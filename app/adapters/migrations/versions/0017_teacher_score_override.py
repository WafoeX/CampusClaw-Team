"""追加教师最终分覆盖及只增历史，不改既有规则评分。"""

from alembic import op
from sqlalchemy import inspect

from app.adapters.score_override_schema_v17 import TABLES

revision = "0017_teacher_score_override"
down_revision = "0016_teaching_job_audit_data"

SUBMISSION_INDEX = "uq_quiz_submissions_class_id"


def upgrade():
    connection = op.get_bind()
    indexes = {
        item["name"] for item in inspect(connection).get_indexes("quiz_submissions")
    }
    if SUBMISSION_INDEX not in indexes:
        op.create_index(
            SUBMISSION_INDEX,
            "quiz_submissions",
            ["class_id", "id"],
            unique=True,
        )
    for table in TABLES:
        table.create(connection, checkfirst=True)


def downgrade():
    connection = op.get_bind()
    if not connection.engine.url.database.startswith("campusclaw_test_"):
        raise ValueError("只允许在合成隔离库物理降级教师改分结构")
    for table in reversed(TABLES):
        table.drop(connection, checkfirst=True)
    indexes = {
        item["name"] for item in inspect(connection).get_indexes("quiz_submissions")
    }
    if SUBMISSION_INDEX in indexes:
        op.drop_index(SUBMISSION_INDEX, table_name="quiz_submissions")
