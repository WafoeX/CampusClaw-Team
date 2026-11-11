"""工具配置、发现与审批使用调用方的短事务。"""

from sqlalchemy import delete, exists, func, insert, select, update

from app.adapters.tool_audit import append_tool_result
from app.adapters.tool_schema_v11 import (
    approvals,
    attempts,
    connectors,
    discoveries,
    results,
)


class ToolRepository:
    def list(self, connection, class_id, page, size):
        query = select(connectors).where(
            connectors.c.class_id == class_id, connectors.c.deleted_at.is_(None)
        )
        total = connection.scalar(select(func.count()).select_from(query.subquery()))
        items = (
            connection.execute(
                query.order_by(connectors.c.created_at.desc(), connectors.c.id.desc())
                .limit(size)
                .offset((page - 1) * size)
            )
            .mappings()
            .all()
        )
        return items, total

    def connector(self, connection, class_id, connector_id, *, lock=False):
        query = select(connectors).where(
            connectors.c.class_id == class_id,
            connectors.c.id == connector_id,
            connectors.c.deleted_at.is_(None),
        )
        return (
            connection.execute(query.with_for_update() if lock else query)
            .mappings()
            .one_or_none()
        )

    def create(self, connection, row):
        connection.execute(insert(connectors).values(row))

    def reference(self, connection, class_id, alias, name):
        query = (
            select(
                connectors,
                discoveries.c.name,
                discoveries.c.definition,
                discoveries.c.fingerprint,
                discoveries.c.enabled,
                discoveries.c.generation.label("tool_generation"),
                exists()
                .where(
                    approvals.c.class_id == connectors.c.class_id,
                    approvals.c.connector_id == connectors.c.id,
                    approvals.c.name == name,
                )
                .label("previously_approved"),
            )
            .outerjoin(
                discoveries,
                (discoveries.c.class_id == connectors.c.class_id)
                & (discoveries.c.connector_id == connectors.c.id)
                & (discoveries.c.name == name),
            )
            .where(connectors.c.class_id == class_id, connectors.c.alias == alias)
            .with_for_update()
        )
        return connection.execute(query).mappings().one_or_none()

    def begin_attempt(self, connection, values):
        connection.execute(insert(attempts).values(values))

    def complete_attempt(self, connection, class_id, attempt_id, **values):
        return append_tool_result(connection, class_id, attempt_id, **values)

    def audit(self, connection, class_id, now, page, size):
        query = (
            select(
                attempts.c.tool_name,
                connectors.c.alias,
                results.c.outcome,
                results.c.reason,
                results.c.duration_ms,
                results.c.created_at,
            )
            .join(attempts, results.c.attempt_id == attempts.c.id)
            .outerjoin(connectors, attempts.c.connector_id == connectors.c.id)
            .where(results.c.class_id == class_id, attempts.c.expires_at > now)
        )
        total = connection.scalar(select(func.count()).select_from(query.subquery()))
        items = (
            connection.execute(
                query.order_by(results.c.created_at.desc(), results.c.attempt_id.desc())
                .limit(size)
                .offset((page - 1) * size)
            )
            .mappings()
            .all()
        )
        return items, total

    def set_state(self, connection, connector, **changes):
        connection.execute(
            update(connectors)
            .where(
                connectors.c.class_id == connector["class_id"],
                connectors.c.id == connector["id"],
            )
            .values(changes)
        )

    def discovery(self, connection, connector):
        return (
            connection.execute(
                select(discoveries)
                .where(
                    discoveries.c.class_id == connector["class_id"],
                    discoveries.c.connector_id == connector["id"],
                )
                .order_by(discoveries.c.name)
            )
            .mappings()
            .all()
        )

    def replace_discovery(self, connection, connector, rows):
        connection.execute(
            delete(discoveries).where(
                discoveries.c.class_id == connector["class_id"],
                discoveries.c.connector_id == connector["id"],
            )
        )
        if rows:
            connection.execute(insert(discoveries), rows)

    def review(self, connection, row, event):
        connection.execute(insert(approvals).values(event))
        connection.execute(
            update(discoveries)
            .where(
                discoveries.c.class_id == row["class_id"],
                discoveries.c.connector_id == row["connector_id"],
                discoveries.c.name == row["name"],
                discoveries.c.generation == row["generation"],
            )
            .values(approved=True, enabled=event["enabled"])
        )
