from datetime import timedelta

from sqlalchemy import delete, func, insert, select, text, update
from sqlalchemy.dialects.mysql import insert as mysql_insert

from app.adapters.auth_schema_v1 import classes
from app.adapters.index_receipts import record_cleanup
from app.adapters.index_schema_v5 import chunks, materials
from app.adapters.index_schema_v6 import operations
from app.adapters.index_schema_v7 import builds, tombstones
from app.adapters.material_repository import MaterialRepository
from app.adapters.material_schema_v2 import bodies


class IndexRepository(MaterialRepository):
    record_cleanup = staticmethod(record_cleanup)

    def lock_class(self, connection, class_id):
        connection.execute(
            select(classes.c.id).where(classes.c.id == class_id).with_for_update()
        ).one()

    def now(self, connection):
        return connection.scalar(select(func.utc_timestamp(6)))

    def lock_material(self, connection, class_id, material_id):
        return (
            connection.execute(
                select(materials)
                .where(materials.c.class_id == class_id, materials.c.id == material_id)
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )

    def source(self, connection, material_id):
        return connection.scalar(
            select(bodies.c.content).where(bodies.c.material_id == material_id)
        )

    def operation(self, connection, identity, material_id, key):
        return (
            connection.execute(
                select(operations)
                .where(
                    operations.c.class_id == identity.class_id,
                    operations.c.actor_id == identity.subject_id,
                    operations.c.material_id == material_id,
                    operations.c.request_key == key,
                )
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )

    def save_operation(
        self, connection, identity, material_id, key, fingerprint, build_id, expires
    ):
        connection.execute(
            text(
                "DELETE FROM material_index_operations WHERE expires_at < UTC_TIMESTAMP(6) LIMIT 100"
            )
        )
        statement = mysql_insert(operations).values(
            class_id=identity.class_id,
            actor_id=identity.subject_id,
            material_id=material_id,
            request_key=key,
            fingerprint=fingerprint,
            build_id=build_id,
            expires_at=expires,
        )
        connection.execute(
            statement.on_duplicate_key_update(
                fingerprint=statement.inserted.fingerprint,
                build_id=statement.inserted.build_id,
                expires_at=statement.inserted.expires_at,
            )
        )

    def active_builds(self, connection, class_id):
        return (
            connection.execute(
                select(builds)
                .where(
                    builds.c.class_id == class_id,
                    builds.c.status.in_(("pending", "building")),
                )
                .with_for_update()
            )
            .mappings()
            .all()
        )

    def expired(self):
        with self.engine.connect() as connection:
            return (
                connection.execute(
                    select(builds)
                    .where(
                        builds.c.status.in_(("pending", "building")),
                        builds.c.lease_expires_at <= func.utc_timestamp(6),
                    )
                    .order_by(builds.c.lease_expires_at, builds.c.id)
                    .limit(100)
                )
                .mappings()
                .all()
            )

    def build(self, connection, class_id, material_id, build_id):
        return (
            connection.execute(
                select(builds)
                .where(
                    builds.c.class_id == class_id,
                    builds.c.material_id == material_id,
                    builds.c.id == build_id,
                )
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )

    def list_builds(self, connection, class_id, material_id):
        return (
            connection.execute(
                select(builds)
                .where(
                    builds.c.class_id == class_id,
                    builds.c.material_id == material_id,
                )
                .order_by(builds.c.index_version.desc())
                .limit(20)
            )
            .mappings()
            .all()
        )

    def create_build(self, connection, fields, source_chunks):
        connection.execute(insert(builds).values(fields))
        connection.execute(
            update(materials)
            .where(materials.c.id == fields["material_id"])
            .values(desired_index_version=fields["index_version"])
        )
        connection.execute(
            insert(chunks),
            [
                {
                    key: fields[key]
                    for key in (
                        "class_id",
                        "material_id",
                        "source_version",
                        "index_version",
                        "index_config_version",
                    )
                }
                | {
                    "id": chunk.id,
                    "ordinal": chunk.ordinal,
                    "start_offset": chunk.start,
                    "end_offset": chunk.end,
                    "content": chunk.text,
                }
                for chunk in source_chunks
            ],
        )

    def update_build(self, connection, build_id, **values):
        connection.execute(update(builds).where(builds.c.id == build_id).values(values))

    def publish(self, connection, row, *, vector_ready):
        result = connection.execute(
            update(materials)
            .where(
                materials.c.class_id == row["class_id"],
                materials.c.id == row["material_id"],
                materials.c.content_version == row["source_version"],
                materials.c.desired_index_version == row["index_version"],
            )
            .values(
                active_index_version=row["index_version"], vector_ready=vector_ready
            )
        )
        return result.rowcount == 1

    def retire(self, connection, row, now):
        others = (
            connection.execute(
                select(builds).where(
                    builds.c.class_id == row["class_id"],
                    builds.c.material_id == row["material_id"],
                    builds.c.index_version != row["index_version"],
                    builds.c.status != "superseded",
                )
            )
            .mappings()
            .all()
        )
        for old in others:
            old_chunks = (
                connection.execute(
                    select(chunks).where(
                        chunks.c.class_id == old["class_id"],
                        chunks.c.material_id == old["material_id"],
                        chunks.c.index_version == old["index_version"],
                    )
                )
                .mappings()
                .all()
            )
            if old_chunks:
                connection.execute(
                    insert(tombstones),
                    [
                        {
                            key: part[key]
                            for key in (
                                "id",
                                "class_id",
                                "material_id",
                                "source_version",
                                "index_version",
                                "index_config_version",
                            )
                        }
                        | {"created_at": now, "expires_at": now + timedelta(days=90)}
                        for part in old_chunks
                    ],
                )
            record_cleanup(connection, old, now)
            self.delete_chunks(connection, old)
            self.update_build(
                connection, old["id"], status="superseded", updated_at=now
            )

    def next_version(self, connection, class_id, material_id):
        return (
            connection.scalar(
                select(func.max(builds.c.index_version)).where(
                    builds.c.class_id == class_id,
                    builds.c.material_id == material_id,
                )
            )
            or 0
        ) + 1

    def delete_chunks(self, connection, row):
        connection.execute(
            delete(chunks).where(
                chunks.c.class_id == row["class_id"],
                chunks.c.material_id == row["material_id"],
                chunks.c.index_version == row["index_version"],
            )
        )
