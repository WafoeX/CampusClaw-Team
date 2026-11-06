from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.dialects.mysql import insert as mysql_insert

from app.adapters.auth_schema_v1 import accounts, auth_sessions
from app.adapters.chapter_schema_v4 import materials
from app.adapters.index_receipts import record_cleanup
from app.adapters.index_schema_v5 import chunks
from app.adapters.index_schema_v6 import operations
from app.adapters.index_schema_v7 import builds, tombstones
from app.adapters.material_schema_v2 import bodies, deletions, uploads


class MaterialRepository:
    def __init__(self, engine):
        self.engine = engine

    def transaction(self):
        return self.engine.begin()

    def list(self, class_id, page, page_size):
        where = materials.c.class_id == class_id
        with self.engine.connect() as connection:
            total = connection.scalar(
                select(func.count()).select_from(materials).where(where)
            )
            rows = (
                connection.execute(
                    select(materials)
                    .where(where)
                    .order_by(materials.c.sort_order, materials.c.id)
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
                .mappings()
                .all()
            )
        return rows, total

    def read(self, class_id, material_id):
        with self.engine.connect() as connection:
            return (
                connection.execute(
                    select(materials, bodies.c.content)
                    .select_from(
                        materials.join(bodies, materials.c.id == bodies.c.material_id)
                    )
                    .where(self._scope(class_id, material_id))
                )
                .mappings()
                .one_or_none()
            )

    @staticmethod
    def _scope(class_id, material_id):
        return (materials.c.class_id == class_id) & (materials.c.id == material_id)

    def lock_actor(self, connection, account_id, digest, now):
        # 与登录、注销、停用及改密使用同一账号锁。
        actor = connection.execute(
            select(accounts.c.class_id, accounts.c.role, accounts.c.enabled)
            .where(accounts.c.id == account_id)
            .with_for_update()
        ).one_or_none()
        if actor is None or not actor.enabled:
            return None
        session = connection.scalar(
            select(auth_sessions.c.account_id)
            .where(
                auth_sessions.c.account_id == account_id,
                auth_sessions.c.token_digest == digest,
                auth_sessions.c.revoked_at.is_(None),
                auth_sessions.c.expires_at > now(),
            )
            .with_for_update()
        )
        return actor if session is not None else None

    def lock_material(self, connection, class_id, material_id):
        return (
            connection.execute(
                select(materials)
                .where(self._scope(class_id, material_id))
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )

    def revise(self, connection, material_id, changes):
        connection.execute(
            update(materials).where(materials.c.id == material_id).values(changes)
        )

    @staticmethod
    def _upload_scope(class_id, creator_id, key):
        return (
            (uploads.c.class_id == class_id)
            & (uploads.c.creator_id == creator_id)
            & (uploads.c.request_key == key)
        )

    def lock_upload(self, connection, class_id, creator_id, key):
        return (
            connection.execute(
                select(uploads)
                .where(self._upload_scope(class_id, creator_id, key))
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )

    def create(self, connection, fields, content, upload):
        connection.execute(insert(materials).values(fields))
        connection.execute(
            insert(bodies).values(material_id=fields["id"], content=content)
        )
        statement = mysql_insert(uploads).values(upload)
        connection.execute(
            statement.on_duplicate_key_update(
                fingerprint=statement.inserted.fingerprint,
                material_id=statement.inserted.material_id,
                result=statement.inserted.result,
                deleted=False,
                expires_at=statement.inserted.expires_at,
            )
        )

    def remove(self, connection, material_id, deleted_at):
        indexed = (
            connection.execute(
                select(builds).where(builds.c.material_id == material_id)
            )
            .mappings()
            .all()
        )
        for row in indexed:
            record_cleanup(connection, row, deleted_at)
        connection.execute(delete(chunks).where(chunks.c.material_id == material_id))
        connection.execute(
            delete(tombstones).where(tombstones.c.material_id == material_id)
        )
        connection.execute(delete(builds).where(builds.c.material_id == material_id))
        connection.execute(
            delete(operations).where(operations.c.material_id == material_id)
        )
        receipt = mysql_insert(deletions).values(
            material_id=material_id, deleted_at=deleted_at
        )
        connection.execute(
            receipt.on_duplicate_key_update(deleted_at=deletions.c.deleted_at)
        )
        connection.execute(
            update(uploads)
            .where(uploads.c.material_id == material_id)
            .values(deleted=True, result=None)
        )
        connection.execute(delete(bodies).where(bodies.c.material_id == material_id))
        connection.execute(delete(materials).where(materials.c.id == material_id))

    def deletion_manifest(self):
        with self.engine.connect() as connection:
            return (
                connection.execute(
                    select(deletions).order_by(
                        deletions.c.deleted_at, deletions.c.material_id
                    )
                )
                .mappings()
                .all()
            )

    def replay_deletions(self, receipts):
        with self.engine.begin() as connection:
            for material_id, deleted_at in receipts:
                self.remove(connection, material_id, deleted_at)
