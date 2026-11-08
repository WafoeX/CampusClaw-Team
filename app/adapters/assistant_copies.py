"""资料删除事务内的私人副本清理；不提供读取或绕过身份的业务入口。"""

from sqlalchemy import case, select, update

from app.adapters.assistant_schema_v8 import (
    citations,
    feedback,
    messages,
    operations,
    runs,
)


def redact_material_copies(connection, material_id, now):
    # 分批定位，正文清除与原文删除共用调用者事务，不发出任何外部请求。
    while True:
        affected = connection.execute(
            select(messages.c.operation_id, messages.c.id)
            .join(citations, citations.c.message_id == messages.c.id)
            .where(
                citations.c.material_id == material_id, citations.c.status != "deleted"
            )
            .limit(100)
        ).all()
        if not affected:
            return
        operation_ids = {row.operation_id for row in affected}
        message_ids = {row.id for row in affected}
        connection.execute(
            update(operations)
            .where(operations.c.id.in_(operation_ids))
            .values(
                input_payload=None,
                status="revoked",
                lease_token=None,
                lease_expires_at=None,
                updated_at=now,
            )
        )
        connection.execute(
            update(runs)
            .where(runs.c.operation_id.in_(operation_ids))
            .values(
                details=None,
                updated_at=now,
            )
        )
        connection.execute(
            update(runs)
            .where(runs.c.operation_id.in_(operation_ids), runs.c.status == "succeeded")
            .values(status="revoked")
        )
        connection.execute(
            update(messages)
            .where(messages.c.operation_id.in_(operation_ids))
            .values(
                content=None,
                content_state="revoked",
            )
        )
        # 组合回答被撤销后，其余来源摘录也不再从该回答的副本返回。
        connection.execute(
            update(citations)
            .where(citations.c.message_id.in_(message_ids))
            .values(
                title=None,
                excerpt=None,
                status=case(
                    (citations.c.status == "deleted", "deleted"), else_="revoked"
                ),
            )
        )
        connection.execute(
            update(citations)
            .where(
                citations.c.message_id.in_(message_ids),
                citations.c.material_id == material_id,
            )
            .values(status="deleted")
        )
        connection.execute(
            update(feedback)
            .where(feedback.c.message_id.in_(message_ids))
            .values(
                note=None,
                status="unavailable",
                revision=feedback.c.revision + 1,
                updated_at=now,
            )
        )
