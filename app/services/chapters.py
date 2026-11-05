from datetime import timedelta
from hashlib import sha256
from uuid import uuid4

from app.services.access import AccessDenied
from app.services.auth import digest_cookie, invalid_session, utc_now
from app.services.materials import material_metadata, missing, unavailable


def chapter_metadata(row):
    return {key: row[key] for key in ("id", "name", "sort_order", "revision")}


def conflict(message="资料或章节已更新，请刷新后重试"):
    return AccessDenied(409, 1400, message)


class ChapterService:
    def __init__(self, repository, database_error, clock=utc_now):
        self.repository = repository
        self.database_error = database_error
        self.clock = clock

    def list(self, identity):
        try:
            rows = self.repository.list_chapters(identity.class_id)
        except self.database_error:
            raise unavailable() from None
        return {
            "items": [chapter_metadata(row) for row in rows]
            + [{"id": "uncategorized", "name": "未分类"}],
            "total": len(rows) + 1,
        }

    def read(self, identity, chapter_id):
        try:
            row = self.repository.read_chapter(identity.class_id, chapter_id)
        except self.database_error:
            raise unavailable() from None
        if row is None:
            raise missing()
        return chapter_metadata(row)

    def list_materials(self, identity, chapter_id, page, page_size):
        if chapter_id is not None:
            self.read(identity, chapter_id)
        try:
            rows, total = self.repository.list_materials(
                identity.class_id, chapter_id, page, page_size
            )
        except self.database_error:
            raise unavailable() from None
        return {
            "items": [material_metadata(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def _writer(self, connection, identity, cookie):
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

    def _chapter(self, connection, identity, chapter_id):
        row = self.repository.lock_chapter(connection, identity.class_id, chapter_id)
        if row is None:
            raise missing()
        return row

    def _replay(self, connection, identity, method, resource_id, key, fingerprint):
        previous = self.repository.lock_operation(
            connection, identity.class_id, identity.subject_id, method, resource_id, key
        )
        if previous is None or previous["expires_at"] <= self.clock():
            return None
        if previous["fingerprint"] != fingerprint:
            raise conflict("请求标识已用于不同内容")
        return previous["result"]

    def _save(
        self, connection, identity, method, resource_id, key, fingerprint, result
    ):
        now = self.clock()
        self.repository.save_operation(
            connection,
            {
                "class_id": identity.class_id,
                "actor_id": identity.subject_id,
                "method": method,
                "resource_id": resource_id,
                "request_key": key,
                "fingerprint": fingerprint,
                "result": result,
                "expires_at": now + timedelta(hours=24),
            },
            now,
        )

    def create(self, identity, cookie, key, name, sort_order):
        fingerprint = sha256(f"{name}\0{sort_order}".encode()).digest()
        try:
            with self.repository.transaction() as connection:
                self._writer(connection, identity, cookie)
                prior = self._replay(
                    connection, identity, "POST", "chapters", key, fingerprint
                )
                if prior is not None:
                    self._chapter(connection, identity, prior["id"])
                    return prior
                now = self.clock()
                row = {
                    "id": str(uuid4()),
                    "class_id": identity.class_id,
                    "creator_id": identity.subject_id,
                    "name": name,
                    "sort_order": sort_order,
                    "revision": 1,
                    "created_at": now,
                    "updated_at": now,
                }
                self.repository.insert_chapter(connection, row)
                result = chapter_metadata(row)
                self._save(
                    connection, identity, "POST", "chapters", key, fingerprint, result
                )
                return result
        except self.database_error:
            raise unavailable() from None

    def revise(self, identity, cookie, chapter_id, revision, changes):
        try:
            with self.repository.transaction() as connection:
                self._writer(connection, identity, cookie)
                row = self._chapter(connection, identity, chapter_id)
                if row["revision"] != revision:
                    raise conflict()
                if any(row[key] != value for key, value in changes.items()):
                    changes = {
                        **changes,
                        "revision": revision + 1,
                        "updated_at": self.clock(),
                    }
                    self.repository.update_chapter(connection, chapter_id, changes)
                return chapter_metadata(dict(row) | changes)
        except self.database_error:
            raise unavailable() from None

    def remove(self, identity, cookie, chapter_id, revision):
        try:
            with self.repository.transaction() as connection:
                self._writer(connection, identity, cookie)
                row = self._chapter(connection, identity, chapter_id)
                if row["revision"] != revision:
                    raise conflict()
                self.repository.clear_chapter(
                    connection, identity.class_id, chapter_id, self.clock()
                )
        except self.database_error:
            raise unavailable() from None
        return {"id": chapter_id, "deleted": True}

    def assign(self, identity, cookie, key, material_id, chapter_id, revision):
        fingerprint = sha256(f"{chapter_id}\0{revision}".encode()).digest()
        try:
            with self.repository.transaction() as connection:
                self._writer(connection, identity, cookie)
                # 归类和删章按同一顺序锁定章节、资料。
                if chapter_id is not None:
                    self._chapter(connection, identity, chapter_id)
                row = self.repository.lock_material(
                    connection, identity.class_id, material_id
                )
                if row is None:
                    raise missing()
                prior = self._replay(
                    connection, identity, "PUT", material_id, key, fingerprint
                )
                if prior is not None:
                    return prior
                if row["revision"] != revision:
                    raise conflict()
                if row["chapter_id"] != chapter_id:
                    self.repository.assign(
                        connection, material_id, chapter_id, revision, self.clock()
                    )
                    row = dict(row) | {
                        "chapter_id": chapter_id,
                        "revision": revision + 1,
                    }
                result = material_metadata(row)
                self._save(
                    connection, identity, "PUT", material_id, key, fingerprint, result
                )
                return result
        except self.database_error:
            raise unavailable() from None
