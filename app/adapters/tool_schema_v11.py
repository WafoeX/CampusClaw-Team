"""0011：本班工具连接、发现、审批及只增调用审计。"""

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
)

from app.adapters.assistant_schema_v8 import metadata as upstream
from app.adapters.auth_schema_v1 import utc_timestamp

metadata = MetaData()
for table in (upstream.tables["classes"], upstream.tables["accounts"]):
    table.to_metadata(metadata)

OPTIONS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}

connectors = Table(
    "tool_connectors",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("class_id", String(36), nullable=False),
    Column("creator_id", String(36), nullable=False),
    Column("alias", String(63), nullable=False),
    Column("directory_key", String(63), nullable=False),
    Column("directory_version", String(64), nullable=False),
    Column("generation", Integer, nullable=False),
    Column("status", String(12), nullable=False),
    Column("created_at", utc_timestamp, nullable=False),
    Column("updated_at", utc_timestamp, nullable=False),
    Column("deleted_at", utc_timestamp),
    ForeignKeyConstraint(
        ["class_id", "creator_id"],
        ["accounts.class_id", "accounts.id"],
        name="fk_tool_connectors_creator",
    ),
    UniqueConstraint("class_id", "id", name="uq_tool_connectors_class_id"),
    UniqueConstraint("class_id", "alias", name="uq_tool_connectors_alias"),
    CheckConstraint("generation >= 0", name="ck_tool_connectors_generation"),
    CheckConstraint(
        "status IN ('connecting','connected','disconnected')",
        name="ck_tool_connectors_status",
    ),
    CheckConstraint(
        "deleted_at IS NULL OR status = 'disconnected'",
        name="ck_tool_connectors_deleted",
    ),
    Index("ix_tool_connectors_list", "class_id", "created_at", "id"),
    **OPTIONS,
)


def connector_fk(name):
    return ForeignKeyConstraint(
        ["class_id", "connector_id"],
        ["tool_connectors.class_id", "tool_connectors.id"],
        name=name,
    )


discoveries = Table(
    "tool_discoveries",
    metadata,
    Column("connector_id", String(36), primary_key=True),
    Column("name", String(64), primary_key=True),
    Column("class_id", String(36), nullable=False),
    Column("generation", Integer, nullable=False),
    Column("fingerprint", String(64), nullable=False),
    Column("definition", JSON, nullable=False),
    Column("approved", Boolean, nullable=False),
    Column("enabled", Boolean, nullable=False),
    connector_fk("fk_tool_discoveries_connector"),
    CheckConstraint("generation >= 1", name="ck_tool_discoveries_generation"),
    CheckConstraint("NOT enabled OR approved", name="ck_tool_discoveries_enabled"),
    **OPTIONS,
)

approvals = Table(
    "tool_approvals",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("class_id", String(36), nullable=False),
    Column("connector_id", String(36), nullable=False),
    Column("name", String(64), nullable=False),
    Column("generation", Integer, nullable=False),
    Column("fingerprint", String(64), nullable=False),
    Column("definition", JSON, nullable=False),
    Column("teacher_id", String(36), nullable=False),
    Column("enabled", Boolean, nullable=False),
    Column("created_at", utc_timestamp, nullable=False),
    connector_fk("fk_tool_approvals_connector"),
    ForeignKeyConstraint(
        ["class_id", "teacher_id"],
        ["accounts.class_id", "accounts.id"],
        name="fk_tool_approvals_teacher",
    ),
    CheckConstraint("generation >= 1", name="ck_tool_approvals_generation"),
    Index("ix_tool_approvals_tool", "connector_id", "name", "created_at", "id"),
    **OPTIONS,
)

attempts = Table(
    "tool_attempts",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("class_id", String(36), ForeignKey("classes.id"), nullable=False),
    Column("actor_id", String(36), nullable=False),
    Column("session_id", String(36), nullable=False),
    Column("run_id", String(36), nullable=False),
    Column("connector_id", String(36)),
    Column("tool_name", String(64)),
    Column("generation", Integer),
    Column("fingerprint", String(64)),
    Column("round_number", Integer, nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("send_permitted", Boolean, nullable=False),
    Column("request_id", String(64), nullable=False),
    Column("created_at", utc_timestamp, nullable=False),
    Column("recover_at", utc_timestamp, nullable=False),
    Column("expires_at", utc_timestamp, nullable=False),
    connector_fk("fk_tool_attempts_connector"),
    UniqueConstraint("class_id", "id", name="uq_tool_attempts_class_id"),
    UniqueConstraint(
        "class_id",
        "run_id",
        "round_number",
        "ordinal",
        name="uq_tool_attempts_proposal",
    ),
    CheckConstraint("round_number BETWEEN 0 AND 2", name="ck_tool_attempts_round"),
    CheckConstraint("ordinal >= 1", name="ck_tool_attempts_ordinal"),
    CheckConstraint(
        "NOT send_permitted OR (connector_id IS NOT NULL AND tool_name IS NOT NULL "
        "AND generation IS NOT NULL AND fingerprint IS NOT NULL)",
        name="ck_tool_attempts_send",
    ),
    CheckConstraint(
        "created_at <= recover_at AND recover_at < expires_at",
        name="ck_tool_attempts_times",
    ),
    Index("ix_tool_attempts_recovery", "recover_at", "id"),
    Index("ix_tool_attempts_expiry", "expires_at", "id"),
    **OPTIONS,
)

results = Table(
    "tool_results",
    metadata,
    Column("attempt_id", String(36), primary_key=True),
    Column("class_id", String(36), nullable=False),
    Column("outcome", String(10), nullable=False),
    Column("reason", String(24)),
    Column("duration_ms", Integer, nullable=False),
    Column("created_at", utc_timestamp, nullable=False),
    ForeignKeyConstraint(
        ["class_id", "attempt_id"],
        ["tool_attempts.class_id", "tool_attempts.id"],
        name="fk_tool_results_attempt",
        ondelete="CASCADE",
    ),
    CheckConstraint("duration_ms >= 0", name="ck_tool_results_duration"),
    CheckConstraint(
        "(outcome = 'succeeded' AND reason IS NULL) OR "
        "(outcome IN ('rejected','error') AND reason IS NOT NULL)",
        name="ck_tool_results_outcome",
    ),
    Index("ix_tool_results_list", "class_id", "created_at", "attempt_id"),
    **OPTIONS,
)

TABLES = (connectors, discoveries, approvals, attempts, results)
