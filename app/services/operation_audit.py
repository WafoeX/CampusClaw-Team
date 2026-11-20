import json
import re
from datetime import timedelta
from uuid import uuid4

from app.services.access import Identity
from app.services.materials import missing, unavailable

RETENTION = timedelta(days=90)
REQUEST_ID = re.compile(r"[a-f0-9]{32}")


def append_audit(
    repository,
    connection,
    identity,
    now,
    request_id,
    action,
    resource_type,
    *,
    resource_id=None,
    outcome="succeeded",
    skill_id=None,
    total_tokens=None,
    usage_status="not_applicable",
    duration_ms=0,
):
    if request_id is None:
        return
    if not REQUEST_ID.fullmatch(request_id):
        raise ValueError("操作审计请求标识无效")
    record = dict(
        id=str(uuid4()),
        class_id=identity.class_id,
        actor_id=identity.subject_id,
        created_at=now,
        expires_at=now + RETENTION,
        request_id=request_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome,
        skill_id=skill_id,
        total_tokens=total_tokens,
        usage_status=usage_status,
        duration_ms=duration_ms,
    )
    record["event_json"] = json.dumps(
        projection(record), ensure_ascii=True, separators=(",", ":")
    )
    repository.append_operation_audit(connection, record)


def projection(row):
    return {
        key: row[key]
        for key in (
            "id",
            "request_id",
            "actor_id",
            "action",
            "resource_type",
            "resource_id",
            "outcome",
            "skill_id",
            "total_tokens",
            "usage_status",
            "duration_ms",
        )
    } | {"created_at": row["created_at"].isoformat() + "Z"}


class OperationAudit:
    def __init__(self, ai_apps):
        self.ai = ai_apps
        self.repository = ai_apps.repository

    def denied(self, actor, request_id, action, resource_type, duration_ms):
        identity = Identity(actor.id, actor.class_id, frozenset())
        try:
            with self.repository.transaction() as connection:
                append_audit(
                    self.repository,
                    connection,
                    identity,
                    self.ai.clock(),
                    request_id,
                    action,
                    resource_type,
                    outcome="denied",
                    duration_ms=duration_ms,
                )
        except self.ai.database_error:
            return False
        return True

    def list(self, identity, cookie, page, size, end, days, filters, job_id=None):
        try:
            with self.repository.transaction() as connection:
                self.ai._actor(connection, identity, cookie, teacher=True)
                now = self.ai.clock()
                end = end if end is not None else now + timedelta(microseconds=1)
                rows, total = self.repository.list_operation_audit(
                    connection,
                    identity.class_id,
                    now,
                    end - timedelta(days=days),
                    end,
                    filters,
                    page,
                    size,
                    job_id,
                )
        except self.ai.database_error:
            raise unavailable() from None
        return {
            "items": [projection(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": size,
        }

    def read(self, identity, cookie, event_id):
        try:
            with self.repository.transaction() as connection:
                self.ai._actor(connection, identity, cookie, teacher=True)
                row = self.repository.read_operation_audit(
                    connection, identity.class_id, self.ai.clock(), event_id
                )
        except self.ai.database_error:
            raise unavailable() from None
        if row is None:
            raise missing()
        return projection(row)
