"""授权范围召回与二次校验；关键词不依赖嵌入或向量。"""

import time
from contextlib import nullcontext

from app.services.access import AccessDenied
from app.services.auth import invalid_session
from app.services.index_scope import IndexScope
from app.services.materials import missing, unavailable

RRF_K = 60


def rrf(keyword_ids, vector_ids):
    scores = {}
    for ids in (keyword_ids, vector_ids):
        unique = list(dict.fromkeys(ids))
        for rank, chunk_id in enumerate(unique, 1):
            scores[chunk_id] = scores.get(chunk_id, 0) + 1 / (RRF_K + rank)
    return sorted(scores, key=lambda key: (-scores[key], key))


def citation(row):
    return {
        key: row[key]
        for key in (
            "material_id",
            "source_version",
            "index_version",
            "index_config_version",
            "title",
        )
    } | {
        "chunk_id": row["id"],
        "start": row["start_offset"],
        "end": row["end_offset"],
        "text": row["content"],
    }


class RetrievalService:
    def __init__(
        self,
        repository,
        database_error,
        embedding,
        vectors,
        dependency_error,
        current_actor,
        threshold,
        quota=None,
        model_guard=None,
    ):
        self.repository = repository
        self.database_error = database_error
        self.embedding = embedding
        self.vectors = vectors
        self.dependency_error = dependency_error
        self.current_actor = current_actor
        self.threshold = threshold
        self.quota = quota or (lambda identity: None)
        self.model_guard = model_guard or (lambda identity: nullcontext())

    def identity(self, identity, cookie):
        actor = self.current_actor(cookie)
        if (
            actor is None
            or actor.id != identity.subject_id
            or actor.class_id != identity.class_id
        ):
            raise invalid_session()
        if actor.role not in ("teacher", "student"):
            raise AccessDenied(403, 1200, "当前账号无此操作权限")

    def scope(self, identity, chapter_scope):
        if chapter_scope not in (
            None,
            "uncategorized",
        ) and not self.repository.chapter_exists(identity.class_id, chapter_scope):
            raise missing()

    def search(self, identity, cookie, query, mode, chapter_scope, *, deadline=None):
        deadline = deadline or time.monotonic() + 35
        try:
            self.identity(identity, cookie)
            self.scope(identity, chapter_scope)
            keyword = (
                list(self.repository.keyword(identity.class_id, chapter_scope, query))
                if mode in ("keyword", "hybrid")
                else []
            )
            vector = []
            versions = None
            if mode in ("vector", "hybrid"):
                if (
                    self.embedding is None
                    or self.vectors is None
                    or self.threshold is None
                ):
                    raise AccessDenied(503, 1500, "向量检索未就绪，请改用关键词")
                versions = self.repository.versions(identity.class_id, chapter_scope)
                if len(versions) > 1000:
                    raise AccessDenied(
                        429, 1600, "检索范围过大，请缩小章节", retry_after=1
                    )
                self.vectors.available(deadline)
                if any(not row["vector_ready"] for row in versions):
                    raise AccessDenied(
                        503, 1500, "部分资料仅关键词就绪，请改用关键词或缩小范围"
                    )
                scopes = []
                # 构建的配置指纹属于切片，回表读取首片获得该版本配置，不从客户端接收。
                for row in versions:
                    scope = self.repository.version_scope(row)
                    if scope is None:
                        raise AccessDenied(409, 1400, "索引版本已变化，请重新检索")
                    scopes.append(IndexScope(**scope))
                if scopes:
                    with self.model_guard(identity):
                        query_vector = self.embedding.embed_query(
                            query, deadline, before_call=lambda: self.quota(identity)
                        )
                    hits = self.vectors.query(
                        identity.class_id,
                        scopes,
                        query_vector,
                        self.threshold,
                        deadline,
                    )
                    real = {
                        row["id"]: row
                        for row in self.repository.authorized_chunks(
                            identity.class_id,
                            chapter_scope,
                            [hit["id"] for hit in hits],
                        )
                    }
                    for hit in hits:
                        row = real.get(hit["id"])
                        if row is not None:
                            scope = IndexScope(
                                *(
                                    row[key]
                                    for key in (
                                        "class_id",
                                        "material_id",
                                        "source_version",
                                        "index_version",
                                        "index_config_version",
                                    )
                                )
                            )
                            if hit.get("payload") == scope.payload(row["id"]):
                                vector.append(row)
            keyword_ids = [row["id"] for row in keyword]
            vector_ids = [row["id"] for row in vector]
            ids = (
                rrf(keyword_ids, vector_ids)
                if mode == "hybrid"
                else (keyword_ids if mode == "keyword" else vector_ids)
            )
            selected = list(dict.fromkeys(ids))[:8]
            self.identity(identity, cookie)
            self.scope(identity, chapter_scope)
            if versions is not None:
                fresh = self.repository.versions(identity.class_id, chapter_scope)
                fields = (
                    "id",
                    "content_version",
                    "active_index_version",
                    "vector_ready",
                )
                if [tuple(row[key] for key in fields) for row in fresh] != [
                    tuple(row[key] for key in fields) for row in versions
                ]:
                    raise AccessDenied(409, 1400, "检索范围或索引已变化，请重试")
            current = {
                row["id"]: row
                for row in self.repository.authorized_chunks(
                    identity.class_id, chapter_scope, selected
                )
            }
            original = {row["id"]: row for row in keyword + vector}
            if any(
                key not in current
                or any(
                    current[key][field] != original[key][field]
                    for field in (
                        "source_version",
                        "index_version",
                        "index_config_version",
                    )
                )
                for key in selected
            ):
                raise AccessDenied(409, 1400, "来源或范围已变化，请重新检索")
            return {"mode": mode, "items": [citation(current[key]) for key in selected]}
        except self.database_error:
            raise unavailable() from None
        except self.dependency_error:
            raise AccessDenied(503, 1500, "向量依赖暂不可用，请改用关键词") from None

    def recheck(self, identity, cookie, evidence, chapter_scope):
        try:
            self.identity(identity, cookie)
            try:
                self.scope(identity, chapter_scope)
            except AccessDenied as error:
                if error.status == 404:
                    raise AccessDenied(
                        409, 1400, "来源或范围已变化，请重新提问"
                    ) from None
                raise
            current = {
                row["id"]: row
                for row in self.repository.authorized_chunks(
                    identity.class_id,
                    chapter_scope,
                    [item["chunk_id"] for item in evidence],
                )
            }
            for item in evidence:
                row = current.get(item["chunk_id"])
                if (
                    row is None
                    or any(
                        row[field] != item[field]
                        for field in (
                            "material_id",
                            "source_version",
                            "index_version",
                            "index_config_version",
                        )
                    )
                    or row["content"] != item["text"]
                ):
                    raise AccessDenied(409, 1400, "来源或范围已变化，请重新提问")
        except self.database_error:
            raise unavailable() from None

    def open_citation(
        self, identity, cookie, material_id, chunk_id, source_version, index_version
    ):
        try:
            self.identity(identity, cookie)
            source = self.repository.read(identity.class_id, material_id)
            if source is None:
                raise missing()
            rows = self.repository.authorized_chunks(
                identity.class_id, None, [chunk_id]
            )
            for row in rows:
                if (
                    row["material_id"] == material_id
                    and row["source_version"] == source_version
                    and row["index_version"] == index_version
                ):
                    self.identity(identity, cookie)
                    latest = self.repository.read(identity.class_id, material_id)
                    if latest is None:
                        raise missing()
                    if (
                        not self.repository.authorized_chunks(
                            identity.class_id, None, [chunk_id]
                        )
                        or latest["content_version"] != source_version
                    ):
                        raise AccessDenied(409, 1400, "来源已变化，请重新检索")
                    return citation(row) | {
                        "source_text": latest["content"].decode("utf-8-sig")
                    }
            if self.repository.old_citation(
                identity.class_id, material_id, chunk_id, source_version, index_version
            ):
                raise AccessDenied(
                    409, 1400, "来源已重建，请重新检索；旧出处不会跳转到新片段"
                )
            raise missing()
        except self.database_error:
            raise unavailable() from None
