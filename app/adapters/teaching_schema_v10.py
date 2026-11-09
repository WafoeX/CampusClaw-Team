"""0010 教学闭环结构；发布快照及正式评分只增。"""

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
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import VARBINARY

from app.adapters.auth_schema_v1 import digest_type, utc_timestamp
from app.adapters.chapter_schema_v4 import metadata

# 外键引用的上游表均已在 0001–0008 创建；这里只创建 TABLES。

questions = Table(
    "questions",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("class_id", String(36), ForeignKey("classes.id"), nullable=False),
    Column("creator_id", String(36), ForeignKey("accounts.id"), nullable=False),
    Column("current_version", Integer, nullable=False),
    Column("reviewed_version", Integer),
    Column("created_at", utc_timestamp, nullable=False),
    Column("updated_at", utc_timestamp, nullable=False),
    UniqueConstraint("class_id", "id", name="uq_questions_class_id"),
    CheckConstraint("current_version > 0", name="ck_questions_version"),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
)
question_versions = Table(
    "question_versions",
    metadata,
    Column("question_id", String(36), primary_key=True),
    Column("version", Integer, primary_key=True),
    Column("class_id", String(36), nullable=False),
    Column("kind", String(16), nullable=False),
    Column("stem", Text, nullable=False),
    Column("options", JSON, nullable=False),
    Column("answer", String(8), nullable=False),
    Column("explanation", Text, nullable=False),
    Column("source_material_id", String(36)),
    Column("created_at", utc_timestamp, nullable=False),
    ForeignKeyConstraint(
        ["class_id", "question_id"],
        ["questions.class_id", "questions.id"],
        name="fk_question_versions_question_class",
    ),
    ForeignKeyConstraint(
        ["class_id", "source_material_id"],
        ["materials.class_id", "materials.id"],
        name="fk_question_versions_material_class",
    ),
    UniqueConstraint(
        "class_id", "question_id", "version", name="uq_question_versions_class_key"
    ),
    CheckConstraint(
        "kind IN ('single_choice', 'true_false')", name="ck_question_versions_kind"
    ),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
)
question_audits = Table(
    "question_audits",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("class_id", String(36), nullable=False),
    Column("question_id", String(36), nullable=False),
    Column("version", Integer, nullable=False),
    Column("actor_id", String(36), ForeignKey("accounts.id"), nullable=False),
    Column("event", String(12), nullable=False),
    Column("created_at", utc_timestamp, nullable=False),
    ForeignKeyConstraint(
        ["class_id", "question_id"],
        ["questions.class_id", "questions.id"],
        name="fk_question_audits_question_class",
    ),
    CheckConstraint(
        "event IN ('created', 'edited', 'reviewed')", name="ck_question_audits_event"
    ),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
)
quizzes = Table(
    "quizzes",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("class_id", String(36), ForeignKey("classes.id"), nullable=False),
    Column("chapter_id", String(36)),
    Column("creator_id", String(36), ForeignKey("accounts.id"), nullable=False),
    Column("title", String(120), nullable=False),
    Column("deadline_at", utc_timestamp, nullable=False),
    Column("answers_open_at", utc_timestamp, nullable=False),
    Column("published_at", utc_timestamp),
    Column("created_at", utc_timestamp, nullable=False),
    UniqueConstraint("class_id", "id", name="uq_quizzes_class_id"),
    ForeignKeyConstraint(
        ["class_id", "chapter_id"],
        ["chapters.class_id", "chapters.id"],
        name="fk_quizzes_chapter_class",
    ),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
)
quiz_draft_items = Table(
    "quiz_draft_items",
    metadata,
    Column("quiz_id", String(36), primary_key=True),
    Column("position", Integer, primary_key=True),
    Column("class_id", String(36), nullable=False),
    Column("question_id", String(36), nullable=False),
    Column("points", Integer, nullable=False),
    ForeignKeyConstraint(
        ["class_id", "quiz_id"],
        ["quizzes.class_id", "quizzes.id"],
        name="fk_quiz_draft_items_quiz_class",
    ),
    ForeignKeyConstraint(
        ["class_id", "question_id"],
        ["questions.class_id", "questions.id"],
        name="fk_quiz_draft_items_question_class",
    ),
    CheckConstraint("points BETWEEN 1 AND 100", name="ck_quiz_draft_items_points"),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
)
quiz_items = Table(
    "quiz_items",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("quiz_id", String(36), nullable=False),
    Column("class_id", String(36), nullable=False),
    Column("position", Integer, nullable=False),
    Column("question_id", String(36), nullable=False),
    Column("question_version", Integer, nullable=False),
    Column("kind", String(16), nullable=False),
    Column("stem", Text, nullable=False),
    Column("options", JSON, nullable=False),
    Column("answer", String(8), nullable=False),
    Column("explanation", Text, nullable=False),
    Column("source_material_id", String(36)),
    Column("points", Integer, nullable=False),
    Column("scoring_version", Integer, nullable=False),
    UniqueConstraint("class_id", "quiz_id", "position", name="uq_quiz_items_position"),
    UniqueConstraint("class_id", "quiz_id", "id", name="uq_quiz_items_class_key"),
    ForeignKeyConstraint(
        ["class_id", "quiz_id"],
        ["quizzes.class_id", "quizzes.id"],
        name="fk_quiz_items_quiz_class",
    ),
    ForeignKeyConstraint(
        ["class_id", "question_id", "question_version"],
        [
            "question_versions.class_id",
            "question_versions.question_id",
            "question_versions.version",
        ],
        name="fk_quiz_items_question_version_class",
    ),
    ForeignKeyConstraint(
        ["class_id", "source_material_id"],
        ["materials.class_id", "materials.id"],
        name="fk_quiz_items_material_class",
    ),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
)
quiz_participants = Table(
    "quiz_participants",
    metadata,
    Column("quiz_id", String(36), primary_key=True),
    Column("student_id", String(36), primary_key=True),
    Column("class_id", String(36), nullable=False),
    Column("created_at", utc_timestamp, nullable=False),
    UniqueConstraint(
        "class_id", "quiz_id", "student_id", name="uq_quiz_participants_class_key"
    ),
    ForeignKeyConstraint(
        ["class_id", "quiz_id"],
        ["quizzes.class_id", "quizzes.id"],
        name="fk_quiz_participants_quiz_class",
    ),
    ForeignKeyConstraint(
        ["class_id", "student_id"],
        ["accounts.class_id", "accounts.id"],
        name="fk_quiz_participants_student_class",
    ),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
)
quiz_drafts = Table(
    "quiz_drafts",
    metadata,
    Column("quiz_id", String(36), primary_key=True),
    Column("student_id", String(36), primary_key=True),
    Column("class_id", String(36), nullable=False),
    Column("revision", Integer, nullable=False),
    Column("answers", JSON, nullable=False),
    Column("updated_at", utc_timestamp, nullable=False),
    ForeignKeyConstraint(
        ["class_id", "quiz_id", "student_id"],
        [
            "quiz_participants.class_id",
            "quiz_participants.quiz_id",
            "quiz_participants.student_id",
        ],
        name="fk_quiz_drafts_participant",
    ),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
)
quiz_submissions = Table(
    "quiz_submissions",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("quiz_id", String(36), nullable=False),
    Column("student_id", String(36), nullable=False),
    Column("class_id", String(36), nullable=False),
    Column("request_key", VARBINARY(64), nullable=False),
    Column("fingerprint", digest_type, nullable=False),
    Column("answers", JSON, nullable=False),
    Column("accepted_at", utc_timestamp, nullable=False),
    UniqueConstraint(
        "class_id", "quiz_id", "student_id", name="uq_quiz_submissions_once"
    ),
    ForeignKeyConstraint(
        ["class_id", "quiz_id", "student_id"],
        [
            "quiz_participants.class_id",
            "quiz_participants.quiz_id",
            "quiz_participants.student_id",
        ],
        name="fk_quiz_submissions_participant",
    ),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
)
quiz_results = Table(
    "quiz_results",
    metadata,
    Column(
        "submission_id", String(36), ForeignKey("quiz_submissions.id"), primary_key=True
    ),
    Column("score", Integer, nullable=False),
    Column("max_score", Integer, nullable=False),
    Column("details", JSON, nullable=False),
    Column("scoring_version", Integer, nullable=False),
    Column("created_at", utc_timestamp, nullable=False),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
)
quiz_audits = Table(
    "quiz_audits",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("class_id", String(36), nullable=False),
    Column("quiz_id", String(36), nullable=False),
    Column("actor_id", String(36), ForeignKey("accounts.id"), nullable=False),
    Column("event", String(12), nullable=False),
    Column("created_at", utc_timestamp, nullable=False),
    ForeignKeyConstraint(
        ["class_id", "quiz_id"],
        ["quizzes.class_id", "quizzes.id"],
        name="fk_quiz_audits_quiz_class",
    ),
    CheckConstraint(
        "event IN ('created', 'published', 'submitted')", name="ck_quiz_audits_event"
    ),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
)
Index(
    "ix_quizzes_class_published",
    quizzes.c.class_id,
    quizzes.c.published_at,
    quizzes.c.id,
)
TABLES = (
    questions,
    question_versions,
    question_audits,
    quizzes,
    quiz_draft_items,
    quiz_items,
    quiz_participants,
    quiz_drafts,
    quiz_submissions,
    quiz_results,
    quiz_audits,
)
