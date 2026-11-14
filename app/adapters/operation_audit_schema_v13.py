"""0013 去内容操作审计，保留与私人数据独立的生命周期。"""

from sqlalchemy import (
    CheckConstraint,
    Column,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
)

from app.adapters.auth_schema_v1 import utc_timestamp

events = Table(
    "operation_audit_events",
    MetaData(),
    Column("id", String(36), primary_key=True),
    Column("request_id", String(32), nullable=False, unique=True),
    Column("class_id", String(36), nullable=False),
    Column("actor_id", String(36), nullable=False),
    Column("created_at", utc_timestamp, nullable=False),
    Column("action", String(24), nullable=False),
    Column("resource_type", String(16), nullable=False),
    Column("resource_id", String(36)),
    Column("outcome", String(12), nullable=False),
    Column("skill_id", String(36)),
    Column("total_tokens", Integer),
    Column("usage_status", String(16), nullable=False),
    Column("duration_ms", Integer, nullable=False),
    Column("event_json", Text, nullable=False),
    Column("expires_at", utc_timestamp, nullable=False),
    CheckConstraint(
        "outcome IN ('succeeded', 'denied')", name="ck_operation_audit_outcome"
    ),
    CheckConstraint(
        "(usage_status = 'measured' AND total_tokens IS NOT NULL AND total_tokens >= 0)"
        " OR (usage_status IN ('not_applicable','unavailable') AND total_tokens IS NULL)",
        name="ck_operation_audit_usage",
    ),
    CheckConstraint("duration_ms >= 0", name="ck_operation_audit_duration"),
    CheckConstraint("JSON_VALID(event_json)", name="ck_operation_audit_json"),
    Index("ix_operation_audit_class_time", "class_id", "created_at", "id"),
    Index("ix_operation_audit_class_actor", "class_id", "actor_id", "created_at", "id"),
    Index("ix_operation_audit_class_skill", "class_id", "skill_id", "created_at", "id"),
    Index("ix_operation_audit_expiry", "expires_at", "id"),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
)
