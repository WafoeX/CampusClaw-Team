"""0019 学生正式提交持久任务；成功结果仍写入 0010 正式表。"""

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Table,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import VARBINARY

from app.adapters.auth_schema_v1 import digest_type, utc_timestamp
from app.adapters.teaching_schema_v10 import metadata

quiz_submission_jobs = Table(
    "quiz_submission_jobs",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("submission_id", String(36), nullable=False),
    Column("class_id", String(36), nullable=False),
    Column("quiz_id", String(36), nullable=False),
    Column("student_id", String(36), nullable=False),
    Column("request_key", VARBINARY(64), nullable=False),
    Column("fingerprint", digest_type, nullable=False),
    Column("draft_revision", Integer, nullable=False),
    Column("answers", JSON),
    Column("status", String(16), nullable=False),
    Column("attempts", Integer, nullable=False),
    Column("next_attempt_at", utc_timestamp, nullable=False),
    Column("lease_token", String(36)),
    Column("lease_expires_at", utc_timestamp),
    Column("failure_code", String(32)),
    Column("accepted_at", utc_timestamp, nullable=False),
    Column("started_at", utc_timestamp),
    Column("completed_at", utc_timestamp),
    UniqueConstraint("submission_id", name="uq_submission_jobs_submission"),
    UniqueConstraint(
        "class_id",
        "quiz_id",
        "student_id",
        name="uq_submission_jobs_student_quiz",
    ),
    ForeignKeyConstraint(
        ["class_id", "quiz_id", "student_id"],
        [
            "quiz_participants.class_id",
            "quiz_participants.quiz_id",
            "quiz_participants.student_id",
        ],
        name="fk_submission_jobs_participant",
    ),
    CheckConstraint(
        "status IN ('pending','running','succeeded','failed')",
        name="ck_submission_jobs_status",
    ),
    CheckConstraint("attempts BETWEEN 0 AND 5", name="ck_submission_jobs_attempts"),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
)
Index(
    "ix_submission_jobs_claim",
    quiz_submission_jobs.c.status,
    quiz_submission_jobs.c.next_attempt_at,
    quiz_submission_jobs.c.lease_expires_at,
    quiz_submission_jobs.c.accepted_at,
)

TABLES = (quiz_submission_jobs,)
