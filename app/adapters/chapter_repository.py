from sqlalchemy import delete, func, insert, select, text, update
from sqlalchemy.dialects.mysql import insert as mysql_insert

from app.adapters.chapter_schema_v4 import chapter_idempotency, chapters, materials
from app.adapters.material_repository import MaterialRepository


class ChapterRepository(MaterialRepository):
    def list_chapters(self, class_id):
        with self.engine.connect() as connection:
            return (
                connection.execute(
                    select(chapters)
                    .where(chapters.c.class_id == class_id)
                    .order_by(chapters.c.sort_order, chapters.c.id)
                )
                .mappings()
                .all()
            )

    def read_chapter(self, class_id, chapter_id):
        with self.engine.connect() as connection:
            return (
                connection.execute(
                    select(chapters).where(
                        chapters.c.class_id == class_id, chapters.c.id == chapter_id
                    )
                )
                .mappings()
                .one_or_none()
            )

    def list_materials(self, class_id, chapter_id, page, page_size):
        scope = (materials.c.class_id == class_id) & (
            materials.c.chapter_id.is_(None)
            if chapter_id is None
            else materials.c.chapter_id == chapter_id
        )
        with self.engine.connect() as connection:
            total = connection.scalar(
                select(func.count()).select_from(materials).where(scope)
            )
            rows = (
                connection.execute(
                    select(materials)
                    .where(scope)
                    .order_by(materials.c.sort_order, materials.c.id)
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
                .mappings()
                .all()
            )
        return rows, total

    def lock_chapter(self, connection, class_id, chapter_id):
        return (
            connection.execute(
                select(chapters)
                .where(chapters.c.class_id == class_id, chapters.c.id == chapter_id)
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )

    def insert_chapter(self, connection, values):
        connection.execute(insert(chapters).values(values))

    def update_chapter(self, connection, chapter_id, values):
        connection.execute(
            update(chapters).where(chapters.c.id == chapter_id).values(values)
        )

    def clear_chapter(self, connection, class_id, chapter_id, now):
        connection.execute(
            update(materials)
            .where(
                materials.c.class_id == class_id,
                materials.c.chapter_id == chapter_id,
            )
            .values(
                chapter_id=None,
                revision=materials.c.revision + 1,
                updated_at=now,
            )
        )
        connection.execute(delete(chapters).where(chapters.c.id == chapter_id))

    def assign(self, connection, material_id, chapter_id, revision, now):
        connection.execute(
            update(materials)
            .where(materials.c.id == material_id)
            .values(chapter_id=chapter_id, revision=revision + 1, updated_at=now)
        )

    def lock_operation(self, connection, class_id, actor_id, method, resource_id, key):
        return (
            connection.execute(
                select(chapter_idempotency)
                .where(
                    chapter_idempotency.c.class_id == class_id,
                    chapter_idempotency.c.actor_id == actor_id,
                    chapter_idempotency.c.method == method,
                    chapter_idempotency.c.resource_id == resource_id,
                    chapter_idempotency.c.request_key == key,
                )
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )

    def save_operation(self, connection, values, now):
        connection.execute(
            text("DELETE FROM chapter_idempotency WHERE expires_at < :now LIMIT 100"),
            {"now": now},
        )
        statement = mysql_insert(chapter_idempotency).values(values)
        connection.execute(
            statement.on_duplicate_key_update(
                fingerprint=statement.inserted.fingerprint,
                result=statement.inserted.result,
                expires_at=statement.inserted.expires_at,
            )
        )
