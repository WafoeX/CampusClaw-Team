from sqlalchemy import delete, func, insert, select
from sqlalchemy.dialects.mysql import insert as mysql_insert

from app.adapters.operation_audit_schema_v13 import events


class OperationAuditRepositoryMixin:
    @staticmethod
    def append_operation_audit(connection, record):
        if record["outcome"] == "denied":
            statement = mysql_insert(events).values(record)
            connection.execute(statement.on_duplicate_key_update(id=events.c.id))
        else:
            connection.execute(insert(events).values(record))

    @staticmethod
    def list_operation_audit(
        connection, class_id, now, start, end, filters, page, size, job_id=None
    ):
        conditions = [
            events.c.class_id == class_id,
            events.c.expires_at > now,
            events.c.created_at >= start,
            events.c.created_at < end,
            *(events.c[key] == value for key, value in filters.items()),
        ]
        if job_id is not None:
            conditions.extend(
                (
                    events.c.resource_type.in_(("teaching_job", "submission_job")),
                    events.c.resource_id == job_id,
                )
            )
        total = connection.scalar(
            select(func.count()).select_from(events).where(*conditions)
        )
        rows = (
            connection.execute(
                select(events)
                .where(*conditions)
                .order_by(events.c.created_at.desc(), events.c.id.desc())
                .offset((page - 1) * size)
                .limit(size)
            )
            .mappings()
            .all()
        )
        return rows, total

    @staticmethod
    def read_operation_audit(connection, class_id, now, event_id):
        return (
            connection.execute(
                select(events).where(
                    events.c.class_id == class_id,
                    events.c.expires_at > now,
                    events.c.id == event_id,
                )
            )
            .mappings()
            .one_or_none()
        )

    @staticmethod
    def cleanup_operation_audit(connection, now):
        ids = connection.scalars(
            select(events.c.id)
            .where(events.c.expires_at <= now)
            .order_by(events.c.expires_at, events.c.id)
            .limit(100)
            .with_for_update(skip_locked=True)
        ).all()
        if ids:
            connection.execute(delete(events).where(events.c.id.in_(ids)))
        return len(ids)
