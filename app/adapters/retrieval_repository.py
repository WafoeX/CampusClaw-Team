from sqlalchemy import func, select
from sqlalchemy.dialects.mysql import match

from app.adapters.chapter_schema_v4 import chapters
from app.adapters.index_schema_v5 import chunks, materials
from app.adapters.index_schema_v7 import tombstones
from app.adapters.material_repository import MaterialRepository


class RetrievalRepository(MaterialRepository):
    def __init__(self, engine, material_ids=None):
        super().__init__(engine)
        self.material_ids = None if material_ids is None else tuple(material_ids)

    def for_materials(self, material_ids):
        return RetrievalRepository(self.engine, material_ids)

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

    def scope(self, class_id, chapter_scope):
        conditions = [materials.c.class_id == class_id]
        if self.material_ids is not None:
            conditions.append(materials.c.id.in_(self.material_ids))
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

    def teaching_evidence(
        self,
        connection,
        class_id,
        chapter_id,
        *,
        material_id=None,
        ids=None,
        lock=False,
    ):
        statement = (
            select(chunks, materials.c.title)
            .join(materials, chunks.c.material_id == materials.c.id)
            .where(*self.scope(class_id, chapter_id), *self.visible())
        )
        if material_id is not None:
            statement = statement.where(materials.c.id == material_id)
        if ids is not None:
            statement = statement.where(chunks.c.id.in_(ids))
        statement = statement.order_by(chunks.c.ordinal, chunks.c.material_id).limit(8)
        if lock:
            statement = statement.with_for_update()
        return connection.execute(statement).mappings().all()

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
