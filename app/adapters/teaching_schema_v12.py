"""0012：出处快照、持久任务、发件箱、结果和坏消息隔离。"""

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Table,
)
from sqlalchemy.dialects.mysql import BIGINT

from app.adapters.auth_schema_v1 import utc_timestamp
from app.adapters.teaching_schema_v10 import metadata

options = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}

question_sources = Table(
    "teaching_question_sources",
    metadata,
    Column("question_id", String(36), primary_key=True),
    Column("version", Integer, primary_key=True),
    Column("class_id", String(36), nullable=False),
    Column("material_id", String(36), nullable=False),
    Column("snapshot", JSON, nullable=False),
    ForeignKeyConstraint(
        ["class_id", "question_id", "version"],
        [
            "question_versions.class_id",
            "question_versions.question_id",
            "question_versions.version",
        ],
        name="fk_teaching_source_question",
    ),
    ForeignKeyConstraint(
        ["class_id", "material_id"],
        ["materials.class_id", "materials.id"],
        name="fk_teaching_source_material",
        ondelete="CASCADE",
    ),
    **options,
)

jobs = Table(
    "teaching_jobs",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("kind", String(24), nullable=False),
    Column("class_id", String(36), ForeignKey("classes.id"), nullable=False),
    Column("creator_id", String(36), ForeignKey("accounts.id"), nullable=False),
    Column("state", String(16), nullable=False),
    Column("generation", Integer, nullable=False),
    Column("attempt", Integer, nullable=False),
    Column("input", JSON, nullable=False),
    Column("error_code", Integer),
    Column("error_reason", String(32)),
    Column("trace_id", String(36), nullable=False),
    Column("event_id", String(36), nullable=False),
    Column("lease_id", String(36)),
    Column("lease_until", utc_timestamp),
    Column("available_at", utc_timestamp, nullable=False),
    Column("created_at", utc_timestamp, nullable=False),
    Column("updated_at", utc_timestamp, nullable=False),
    CheckConstraint("generation > 0 AND attempt >= 0", name="ck_teaching_job_attempt"),
    CheckConstraint(
        "state IN ('pending','running','retry_wait','succeeded','failed','dead_letter','cancelled')",
        name="ck_teaching_job_state",
    ),
    Index("ix_teaching_job_capacity", "class_id", "kind", "state"),
    Index("ix_teaching_job_expiry", "state", "lease_until", "id"),
    **options,
)

outbox = Table(
    "teaching_outbox",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("job_id", String(36), ForeignKey("teaching_jobs.id")),
    Column("topic", String(64), nullable=False),
    Column("message_key", String(128), nullable=False),
    Column("payload", JSON, nullable=False),
    Column("available_at", utc_timestamp, nullable=False),
    Column("sent_at", utc_timestamp),
    Column("lease_id", String(36)),
    Column("lease_until", utc_timestamp),
    Index("ix_teaching_outbox_ready", "sent_at", "available_at", "id"),
    Index("ix_teaching_outbox_job", "job_id", "topic", "available_at"),
    **options,
)

job_results = Table(
    "teaching_job_results",
    metadata,
    Column("job_id", String(36), ForeignKey("teaching_jobs.id"), primary_key=True),
    Column("result", JSON, nullable=False),
    **options,
)

generated_questions = Table(
    "teaching_generated_questions",
    metadata,
    Column("question_id", String(36), ForeignKey("questions.id"), primary_key=True),
    Column(
        "job_id", String(36), ForeignKey("teaching_jobs.id"), nullable=False, index=True
    ),
    **options,
)

quarantine = Table(
    "teaching_job_quarantine",
    metadata,
    Column("topic", String(64), primary_key=True),
    Column("partition", Integer, primary_key=True),
    Column("offset", BIGINT, primary_key=True),
    Column("recorded_at", utc_timestamp, nullable=False),
    **options,
)

TABLES = (question_sources, jobs, outbox, job_results, generated_questions, quarantine)
