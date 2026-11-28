"""增加学生正式提交持久任务，不回填既有同步提交。"""

from alembic import op

from app.adapters.submission_job_schema_v19 import TABLES

revision = "0019_async_submission_jobs"
down_revision = "0018_mistake_explanation_skill"


def upgrade():
    connection = op.get_bind()
    for table in TABLES:
        table.create(connection, checkfirst=True)


def downgrade():
    connection = op.get_bind()
    if not connection.engine.url.database.startswith("campusclaw_test_"):
        raise ValueError("只允许在合成隔离库物理降级学生提交任务结构")
    for table in reversed(TABLES):
        table.drop(connection, checkfirst=True)
