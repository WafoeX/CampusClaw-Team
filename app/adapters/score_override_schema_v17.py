"""0017 教师最终分覆盖；规则评分保持不可变，改分事件只增。"""

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)

from app.adapters.auth_schema_v1 import utc_timestamp
from app.adapters.teaching_schema_v10 import metadata

score_overrides = Table(
    "quiz_score_overrides",
    metadata,
    Column("submission_id", String(36), primary_key=True),
    Column("class_id", String(36), nullable=False),
    Column("score", Integer, nullable=False),
    Column("reason", Text, nullable=False),
    Column("revision", Integer, nullable=False),
    Column("teacher_id", String(36), ForeignKey("accounts.id"), nullable=False),
    Column("updated_at", utc_timestamp, nullable=False),
    UniqueConstraint(
        "class_id", "submission_id", name="uq_quiz_score_overrides_class_key"
    ),
    ForeignKeyConstraint(
        ["class_id", "submission_id"],
        ["quiz_submissions.class_id", "quiz_submissions.id"],
        name="fk_quiz_score_overrides_submission_class",
    ),
    CheckConstraint("score >= 0", name="ck_quiz_score_overrides_score"),
    CheckConstraint("revision >= 1", name="ck_quiz_score_overrides_revision"),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
)

score_override_events = Table(
    "quiz_score_override_events",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("submission_id", String(36), nullable=False),
    Column("class_id", String(36), nullable=False),
    Column("teacher_id", String(36), ForeignKey("accounts.id"), nullable=False),
    Column("previous_score", Integer, nullable=False),
    Column("score", Integer, nullable=False),
    Column("reason", Text, nullable=False),
    Column("revision", Integer, nullable=False),
    Column("created_at", utc_timestamp, nullable=False),
    UniqueConstraint(
        "submission_id", "revision", name="uq_quiz_score_override_events_revision"
    ),
    ForeignKeyConstraint(
        ["class_id", "submission_id"],
        ["quiz_score_overrides.class_id", "quiz_score_overrides.submission_id"],
        name="fk_quiz_score_override_events_current",
    ),
    CheckConstraint(
        "previous_score >= 0 AND score >= 0",
        name="ck_quiz_score_override_events_scores",
    ),
    CheckConstraint("revision >= 1", name="ck_quiz_score_override_events_revision"),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
)

TABLES = (score_overrides, score_override_events)
