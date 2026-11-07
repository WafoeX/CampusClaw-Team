from sqlalchemy import func, select
from sqlalchemy.dialects.mysql import match

from app.adapters.chapter_schema_v4 import chapters
from app.adapters.index_schema_v5 import chunks, materials
from app.adapters.index_schema_v7 import tombstones
from app.adapters.material_repository import MaterialRepository


class RetrievalRepository(MaterialRepository):
    def chapter_exists(self, class_id, chapter_id):
        with self.engine.connect() as connection:
            return (
                connection.scalar(
                    select(chapters.c.id).where(
                        chapters.c.class_id == class_id, chapters.c.id == chapter_id
                    )
                )
                is not None
            )

    @staticmethod
    def scope(class_id, chapter_scope):
        conditions = [materials.c.class_id == class_id]
        if chapter_scope == "uncategorized":
            conditions.append(materials.c.chapter_id.is_(None))
        elif chapter_scope is not None:
            conditions.append(materials.c.chapter_id == chapter_scope)
        return conditions

    @staticmethod
    def visible():
        return [
            chunks.c.class_id == materials.c.class_id,
            chunks.c.material_id == materials.c.id,
            chunks.c.source_version == materials.c.content_version,
            chunks.c.index_version == materials.c.active_index_version,
        ]

    def versions(self, class_id, chapter_scope):
        with self.engine.connect() as connection:
            return (
                connection.execute(
                    select(materials)
                    .where(
                        *self.scope(class_id, chapter_scope),
                        materials.c.active_index_version.is_not(None),
                    )
                    .order_by(materials.c.id)
                    .limit(1001)
                )
                .mappings()
                .all()
            )

    def version_scope(self, material):
        with self.engine.connect() as connection:
            return (
                connection.execute(
                    select(
                        *(
                            chunks.c[key]
                            for key in (
                                "class_id",
                                "material_id",
                                "source_version",
                                "index_version",
                                "index_config_version",
                            )
                        )
                    )
                    .where(
                        chunks.c.class_id == material["class_id"],
                        chunks.c.material_id == material["id"],
                        chunks.c.source_version == material["content_version"],
                        chunks.c.index_version == material["active_index_version"],
                    )
                    .order_by(chunks.c.ordinal)
                    .limit(1)
                )
                .mappings()
                .one_or_none()
            )

    def keyword(self, class_id, chapter_scope, query):
        score = match(chunks.c.content, against=query, in_natural_language_mode=True)
        statement = (
            select(chunks, materials.c.title)
            .select_from(chunks.join(materials, chunks.c.material_id == materials.c.id))
            .where(*self.scope(class_id, chapter_scope), *self.visible(), score > 0)
            .order_by(score.desc(), chunks.c.id)
            .limit(20)
        )
        with self.engine.connect() as connection:
            return connection.execute(statement).mappings().all()

    def authorized_chunks(self, class_id, chapter_scope, ids):
        if not ids:
            return []
        with self.engine.connect() as connection:
            return (
                connection.execute(
                    select(chunks, materials.c.title)
                    .select_from(
                        chunks.join(materials, chunks.c.material_id == materials.c.id)
                    )
                    .where(
                        *self.scope(class_id, chapter_scope),
                        *self.visible(),
                        chunks.c.id.in_(ids),
                    )
                )
                .mappings()
                .all()
            )

    def old_citation(
        self, class_id, material_id, chunk_id, source_version, index_version
    ):
        with self.engine.connect() as connection:
            return (
                connection.scalar(
                    select(tombstones.c.id).where(
                        tombstones.c.class_id == class_id,
                        tombstones.c.material_id == material_id,
                        tombstones.c.id == chunk_id,
                        tombstones.c.source_version == source_version,
                        tombstones.c.index_version == index_version,
                        tombstones.c.expires_at > func.utc_timestamp(6),
                    )
                )
                is not None
            )
