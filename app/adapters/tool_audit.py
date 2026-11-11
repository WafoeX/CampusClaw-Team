"""追加工具结果、恢复未完成的尝试、清理到期审计。"""

from sqlalchemy import delete, exists, insert, select

from app.adapters.tool_schema_v11 import attempts, results

BATCH_SIZE = 100


def append_tool_result(
    connection, class_id, attempt_id, *, outcome, reason, duration_ms, now
):
    """调用者在同一事务重验权限后追加结果，恢复与正常完成共用尝试锁。"""
    target = connection.execute(
        select(attempts.c.expires_at)
        .where(attempts.c.class_id == class_id, attempts.c.id == attempt_id)
        .with_for_update()
    ).scalar_one_or_none()
    if target is None or target <= now:
        return False
    recorded = connection.execute(
        select(results.c.attempt_id)
        .where(results.c.class_id == class_id, results.c.attempt_id == attempt_id)
        .with_for_update()
    ).scalar_one_or_none()
    if recorded is not None:
        return False
    connection.execute(
        insert(results).values(
            attempt_id=attempt_id,
            class_id=class_id,
            outcome=outcome,
            reason=reason,
            duration_ms=duration_ms,
            created_at=now,
        )
    )
    return True


def cleanup_tool_audit(connection, now):
    expired = connection.scalars(
        select(attempts.c.id)
        .where(attempts.c.expires_at <= now)
        .order_by(attempts.c.expires_at, attempts.c.id)
        .limit(BATCH_SIZE)
        .with_for_update(skip_locked=True)
    ).all()
    if expired:
        connection.execute(delete(attempts).where(attempts.c.id.in_(expired)))
    pending = connection.execute(
        select(attempts.c.class_id, attempts.c.id)
        .where(
            attempts.c.recover_at <= now,
            attempts.c.expires_at > now,
            ~exists().where(results.c.attempt_id == attempts.c.id),
        )
        .order_by(attempts.c.recover_at, attempts.c.id)
        .limit(BATCH_SIZE)
        .with_for_update(skip_locked=True)
    ).all()
    recovered = 0
    for class_id, attempt_id in pending:
        recovered += append_tool_result(
            connection,
            class_id,
            attempt_id,
            outcome="error",
            reason="interrupted",
            duration_ms=0,
            now=now,
        )
    return {"tool_audit_expired": len(expired), "tool_audit_recovered": recovered}
