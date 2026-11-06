from datetime import timedelta

from sqlalchemy import func, or_, select, text, update

from app.adapters.index_schema_v5 import materials
from app.adapters.index_schema_v7 import cleanups


class IndexCleanupRepository:
    def __init__(self, engine):
        self.engine = engine

    def candidates(self):
        with self.engine.connect() as connection:
            return (
                connection.execute(
                    select(cleanups)
                    .where(
                        cleanups.c.status != "manual",
                        or_(
                            cleanups.c.next_attempt_at.is_(None),
                            cleanups.c.next_attempt_at <= func.utc_timestamp(6),
                        ),
                    )
                    .order_by(cleanups.c.updated_at, cleanups.c.id)
                    .limit(100)
                )
                .mappings()
                .all()
            )

    def manual_count(self):
        with self.engine.connect() as connection:
            return connection.scalar(
                select(func.count())
                .select_from(cleanups)
                .where(cleanups.c.status == "manual")
            )

    def prune(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM material_chunk_tombstones WHERE expires_at < UTC_TIMESTAMP(6) LIMIT 100"
                )
            )
            connection.execute(
                text(
                    "DELETE FROM material_index_operations WHERE expires_at < UTC_TIMESTAMP(6) LIMIT 100"
                )
            )
            # 未收敛或待人工凭证不随时间丢弃；完成凭证覆盖 14 天备份及在途窗口后仍保留 90 天。
            connection.execute(
                text(
                    "DELETE FROM material_index_cleanups WHERE status = 'complete' AND created_at < UTC_TIMESTAMP(6) - INTERVAL 90 DAY LIMIT 100"
                )
            )

    def claim(self, receipt_id):
        with self.engine.begin() as connection:
            now = connection.scalar(select(func.utc_timestamp(6)))
            row = (
                connection.execute(
                    select(cleanups)
                    .where(cleanups.c.id == receipt_id)
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if (
                row is None
                or row["status"] == "manual"
                or (row["next_attempt_at"] and row["next_attempt_at"] > now)
            ):
                return None
            active = connection.scalar(
                select(materials.c.id).where(
                    materials.c.class_id == row["class_id"],
                    materials.c.id == row["material_id"],
                    materials.c.active_index_version == row["index_version"],
                    materials.c.vector_ready.is_(True),
                )
            )
            if active or not row["vector_collection"] or row["attempts"] >= 3:
                connection.execute(
                    update(cleanups)
                    .where(cleanups.c.id == receipt_id)
                    .values(status="manual", updated_at=now)
                )
                return None
            connection.execute(
                update(cleanups)
                .where(cleanups.c.id == receipt_id)
                .values(
                    status="retry",
                    attempts=row["attempts"] + 1,
                    next_attempt_at=now + timedelta(seconds=35),
                    updated_at=now,
                )
            )
            return dict(row, attempts=row["attempts"] + 1)

    def finish(self, row, success):
        with self.engine.begin() as connection:
            now = connection.scalar(select(func.utc_timestamp(6)))
            values = {"updated_at": now}
            if success:
                values.update(status="complete", next_attempt_at=None)
            elif row["attempts"] >= 3:
                values.update(status="manual", next_attempt_at=None)
            else:
                values.update(
                    status="retry",
                    next_attempt_at=now
                    + timedelta(minutes=(1, 5, 30)[row["attempts"] - 1]),
                )
            connection.execute(
                update(cleanups)
                .where(
                    cleanups.c.id == row["id"], cleanups.c.attempts == row["attempts"]
                )
                .values(values)
            )

    def touch_complete(self, receipt_id):
        with self.engine.begin() as connection:
            connection.execute(
                update(cleanups)
                .where(cleanups.c.id == receipt_id, cleanups.c.status == "complete")
                .values(updated_at=func.utc_timestamp(6))
            )
