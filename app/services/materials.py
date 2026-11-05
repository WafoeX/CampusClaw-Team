from datetime import timedelta
from hashlib import sha256
from uuid import uuid4

from app.services.access import AccessDenied
from app.services.auth import digest_cookie, invalid_session, utc_now

READ_MATERIALS = "materials:read"
WRITE_MATERIALS = "materials:write"
SEARCH_CHARACTER_LIMIT = 32_000


def material_metadata(row):
    return {
        key: row[key]
        for key in (
            "id",
            "title",
            "sort_order",
            "source_format",
            "media_type",
            "byte_size",
            "character_count",
            "content_version",
            "revision",
        )
    } | {"original_only": row["character_count"] > SEARCH_CHARACTER_LIMIT}


def unavailable():
    return AccessDenied(503, 1500, "依赖服务暂不可用，请稍后重试")


def missing():
    return AccessDenied(404, 1300, "资源不存在或不可访问")


class MaterialService:
    def __init__(self, repository, database_error, clock=utc_now):
        self.repository = repository
        self.database_error = database_error
        self.clock = clock

    def list(self, identity, page, page_size):
        try:
            rows, total = self.repository.list(identity.class_id, page, page_size)
        except self.database_error:
            raise unavailable() from None
        return {
            "items": [material_metadata(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def read(self, identity, material_id):
        try:
            row = self.repository.read(identity.class_id, material_id)
        except self.database_error:
            raise unavailable() from None
        if row is None:
            raise missing()
        return material_metadata(row), row["content"]

    def _check_writer(self, connection, identity, cookie):
        digest = digest_cookie(cookie)
        if digest is None:
            raise invalid_session()
        actor = self.repository.lock_actor(
            connection, identity.subject_id, digest, self.clock
        )
        if actor is None:
            raise invalid_session()
        if actor.role != "teacher" or actor.class_id != identity.class_id:
            raise AccessDenied(403, 1200, "当前账号无此操作权限")

    def _target(self, connection, identity, material_id):
        row = self.repository.lock_material(connection, identity.class_id, material_id)
        if row is None:
            raise missing()
        return row

    def revise(self, identity, cookie, material_id, revision, changes):
        try:
            with self.repository.transaction() as connection:
                self._check_writer(connection, identity, cookie)
                row = self._target(connection, identity, material_id)
                if row["revision"] != revision:
                    raise AccessDenied(409, 1400, "资料已更新，请刷新后重试")
                if any(row[key] != value for key, value in changes.items()):
                    changes = {
                        **changes,
                        "revision": revision + 1,
                        "updated_at": self.clock(),
                    }
                    self.repository.revise(connection, material_id, changes)
                return material_metadata(dict(row) | changes)
        except self.database_error:
            raise unavailable() from None

    def create(self, identity, cookie, key, title, source, media, content, count):
        fingerprint = sha256(
            title.encode("utf-8") + b"\0" + source.encode("ascii") + b"\0" + content
        ).digest()
        try:
            with self.repository.transaction() as connection:
                self._check_writer(connection, identity, cookie)
                previous = self.repository.lock_upload(
                    connection, identity.class_id, identity.subject_id, key
                )
                now = self.clock()
                if previous is not None and previous["expires_at"] > now:
                    if previous["deleted"] or previous["fingerprint"] != fingerprint:
                        raise AccessDenied(
                            409, 1400, "上传标识已使用，请检查资料后重试"
                        )
                    return previous["result"]
                fields = {
                    "id": str(uuid4()),
                    "class_id": identity.class_id,
                    "creator_id": identity.subject_id,
                    "title": title,
                    "sort_order": 0,
                    "source_format": source,
                    "media_type": media,
                    "byte_size": len(content),
                    "character_count": count,
                    "content_version": 1,
                    "revision": 1,
                    "created_at": now,
                    "updated_at": now,
                }
                result = material_metadata(fields)
                self.repository.create(
                    connection,
                    fields,
                    content,
                    {
                        "class_id": identity.class_id,
                        "creator_id": identity.subject_id,
                        "request_key": key,
                        "material_id": fields["id"],
                        "result": result,
                        "fingerprint": fingerprint,
                        "deleted": False,
                        "expires_at": now + timedelta(hours=24),
                    },
                )
                return result
        except self.database_error:
            # 若提交结果未知，由调用方保留同一个键重试。
            raise unavailable() from None

    def remove(self, identity, cookie, material_id):
        try:
            with self.repository.transaction() as connection:
                self._check_writer(connection, identity, cookie)
                self._target(connection, identity, material_id)
                self.repository.remove(connection, material_id, self.clock())
        except self.database_error:
            raise unavailable() from None
