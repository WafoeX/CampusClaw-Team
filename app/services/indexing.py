"""同步构建的 prepare/run/publish 边界；远端副作用在数据库事务外。"""

import time
from contextlib import nullcontext
from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
from uuid import uuid4, uuid5

from app.services.access import AccessDenied
from app.services.chunking import CHUNK_NAMESPACE, split_source
from app.services.index_scope import IndexScope
from app.services.materials import MaterialService, missing, unavailable


def public_build(row):
    return {
        key: row[key]
        for key in (
            "id",
            "material_id",
            "source_version",
            "index_version",
            "index_config_version",
            "status",
            "stage",
        )
    }


class IndexService(MaterialService):
    def __init__(
        self,
        repository,
        database_error,
        embedding,
        vectors,
        dependency_error,
        config_version,
        quota=None,
        model_guard=None,
    ):
        super().__init__(repository, database_error)
        self.embedding = embedding
        self.vectors = vectors
        self.dependency_error = dependency_error
        self.config_version = config_version
        self.quota = quota or (lambda identity: None)
        self.model_guard = model_guard or (lambda identity: nullcontext())

    def _locked(self, connection, identity, cookie, material_id):
        self._check_writer(connection, identity, cookie)
        self.repository.lock_class(connection, identity.class_id)
        return self._target(connection, identity, material_id)

    def status(self, identity, cookie, material_id, build_id=None):
        try:
            with self.repository.transaction() as connection:
                self._locked(connection, identity, cookie, material_id)
                if build_id is None:
                    return {
                        "items": [
                            public_build(row)
                            for row in self.repository.list_builds(
                                connection, identity.class_id, material_id
                            )
                        ]
                    }
                row = self.repository.build(
                    connection, identity.class_id, material_id, build_id
                )
                if row is None:
                    raise missing()
                return public_build(row)
        except self.database_error:
            raise unavailable() from None

    def prepare(self, identity, cookie, material_id, key, config, deadline=None):
        version = sha256(f"{config.version}:{self.config_version}".encode()).hexdigest()
        try:
            source = self.repository.read(identity.class_id, material_id)
            if source is None:
                raise missing()
            # 计算与容量检查在事务外；事务内复核不可变原文版本。
            templates = split_source(
                source["content"], source["source_format"], material_id, 1, config
            )
            with self.repository.transaction() as connection:
                target = self._locked(connection, identity, cookie, material_id)
                if target["content_version"] != source["content_version"]:
                    raise AccessDenied(409, 1400, "原文已更新，请重新构建")
                now = self.repository.now(connection)
                previous = self.repository.operation(
                    connection, identity, material_id, key
                )
                if previous and previous["expires_at"] > now:
                    if previous["fingerprint"] != bytes.fromhex(version):
                        raise AccessDenied(409, 1400, "构建标识已使用，请使用新标识")
                    row = self.repository.build(
                        connection, identity.class_id, material_id, previous["build_id"]
                    )
                    if row is None:
                        raise missing()
                    return dict(row), None
                index_version = self.repository.next_version(
                    connection, identity.class_id, material_id
                )
                parts = [
                    replace(
                        part,
                        id=str(
                            uuid5(
                                CHUNK_NAMESPACE,
                                f"{material_id}:{index_version}:{part.ordinal}",
                            )
                        ),
                    )
                    for part in templates
                ]
                # class 行锁串行化所有实例的同班 prepare，不在模型调用期间持锁。
                for active in self.repository.active_builds(
                    connection, identity.class_id
                ):
                    if active["lease_expires_at"] > now:
                        if active["material_id"] == material_id:
                            raise AccessDenied(409, 1400, "资料正在构建，请查看状态")
                        raise AccessDenied(
                            429, 1600, "本班已有构建，请稍后重试", retry_after=1
                        )
                    self.repository.update_build(
                        connection,
                        active["id"],
                        status="failed",
                        stage="lease_expired",
                        updated_at=now,
                    )
                    self.repository.record_cleanup(connection, active, now)
                row = dict(
                    id=str(uuid4()),
                    class_id=identity.class_id,
                    material_id=material_id,
                    creator_id=identity.subject_id,
                    source_version=target["content_version"],
                    index_version=index_version,
                    index_config_version=version,
                    vector_collection=self.vectors.config.collection,
                    mode=config.mode,
                    window_size=config.window,
                    overlap=config.overlap,
                    status="building",
                    stage="chunks_ready",
                    lease_expires_at=now
                    + timedelta(
                        seconds=max(
                            0,
                            min(
                                35,
                                (deadline or time.monotonic() + 35) - time.monotonic(),
                            ),
                        )
                    ),
                    created_at=now,
                    updated_at=now,
                )
                self.repository.create_build(connection, row, parts)
                self.repository.save_operation(
                    connection,
                    identity,
                    material_id,
                    key,
                    bytes.fromhex(version),
                    row["id"],
                    now + timedelta(hours=24),
                )
                if not target["vector_ready"]:
                    self.repository.publish(connection, row, vector_ready=False)
                    self.repository.retire(connection, row, now)
                return row, parts
        except self.database_error:
            raise unavailable() from None

    def publish(self, identity, cookie, row):
        try:
            with self.repository.transaction() as connection:
                target = self._locked(connection, identity, cookie, row["material_id"])
                now = self.repository.now(connection)
                current = self.repository.build(
                    connection, identity.class_id, row["material_id"], row["id"]
                )
                if (
                    current is None
                    or current["status"] != "building"
                    or current["lease_expires_at"] <= now
                    or target["desired_index_version"] != row["index_version"]
                    or target["content_version"] != row["source_version"]
                    or current["index_config_version"] != row["index_config_version"]
                ):
                    raise AccessDenied(409, 1400, "构建已失效，请重新构建")
                if not self.repository.publish(connection, row, vector_ready=True):
                    raise AccessDenied(409, 1400, "构建已失效，请重新构建")
                self.repository.retire(connection, row, now)
                self.repository.update_build(
                    connection,
                    row["id"],
                    status="published",
                    stage="complete",
                    updated_at=now,
                )
                return public_build(dict(row, status="published", stage="complete"))
        except self.database_error:
            raise unavailable() from None

    def cancel(self, row, stage):
        # 故障收尾不需要已撤销的会话，不能发布或改变原文；只终止本构建。
        try:
            with self.repository.transaction() as connection:
                self.repository.lock_class(connection, row["class_id"])
                target = self.repository.lock_material(
                    connection, row["class_id"], row["material_id"]
                )
                current = self.repository.build(
                    connection, row["class_id"], row["material_id"], row["id"]
                )
                if current is None:
                    return
                if current["status"] != "building":
                    return
                status = (
                    "keyword_only"
                    if target and target["active_index_version"] == row["index_version"]
                    else "failed"
                )
                self.repository.update_build(
                    connection,
                    row["id"],
                    status=status,
                    stage=stage,
                    updated_at=self.repository.now(connection),
                )
                self.repository.record_cleanup(
                    connection, row, self.repository.now(connection)
                )
                if status == "failed":
                    self.repository.delete_chunks(connection, row)
        except self.database_error:
            raise unavailable() from None

    def recover(self):
        try:
            expired = self.repository.expired()
            for row in expired:
                self.cancel(row, "lease_expired")
            return len(expired)
        except self.database_error:
            raise unavailable() from None

    def progress(self, identity, cookie, row, stage):
        try:
            with self.repository.transaction() as connection:
                target = self._locked(connection, identity, cookie, row["material_id"])
                current = self.repository.build(
                    connection, identity.class_id, row["material_id"], row["id"]
                )
                now = self.repository.now(connection)
                if (
                    not current
                    or current["status"] != "building"
                    or current["lease_expires_at"] <= now
                    or target["desired_index_version"] != row["index_version"]
                    or target["content_version"] != row["source_version"]
                ):
                    raise AccessDenied(409, 1400, "构建已失效，请重新构建")
                self.repository.update_build(
                    connection, row["id"], stage=stage, updated_at=now
                )
        except self.database_error:
            raise unavailable() from None

    def run(self, identity, cookie, material_id, key, config):
        deadline = time.monotonic() + 35
        row, parts = self.prepare(identity, cookie, material_id, key, config, deadline)
        if parts is None:
            return public_build(row), 200
        scope = IndexScope(
            row["class_id"],
            material_id,
            row["source_version"],
            row["index_version"],
            row["index_config_version"],
        )
        try:
            stage = "vector_collection"
            self.progress(identity, cookie, row, stage)
            self.vectors.ensure_collection(deadline)
            for offset in range(0, len(parts), 32):
                batch = parts[offset : offset + 32]
                stage = "embedding"
                self.progress(identity, cookie, row, stage)
                with self.model_guard(identity):
                    vectors = self.embedding.embed(
                        [part.text for part in batch],
                        deadline,
                        before_call=lambda: self.quota(identity),
                    )
                stage = "vector_write"
                self.progress(identity, cookie, row, stage)
                self.vectors.write(scope, batch, vectors, deadline)
            stage = "vector_verify"
            self.progress(identity, cookie, row, stage)
            self.vectors.verify(scope, parts, deadline)
            return self.publish(identity, cookie, row), 201
        except self.dependency_error:
            self.cancel(row, stage)
            try:
                self.vectors.delete(scope, deadline)
            except self.dependency_error:
                pass  # 精确清理凭证已提交，补偿器继续复核迟到写入。
            raise unavailable() from None
        except AccessDenied:
            self.cancel(row, "authorization_or_version")
            try:
                self.vectors.delete(scope, deadline)
            except self.dependency_error:
                pass
            raise
