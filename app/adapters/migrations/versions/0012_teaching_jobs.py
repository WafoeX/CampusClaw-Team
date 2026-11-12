"""追加可删除出处与持久任务，保留既有教学数据。"""

from alembic import op

from app.adapters.teaching_schema_v12 import TABLES

revision = "0012_teaching_jobs"
down_revision = "0011_controlled_tools"


def upgrade():
    connection = op.get_bind()
    for table in TABLES:
        table.create(connection, checkfirst=True)


def downgrade():
    connection = op.get_bind()
    if not connection.engine.url.database.startswith("campusclaw_test_"):
        raise ValueError("只允许在合成隔离库物理降级异步教学数据")
    for table in reversed(TABLES):
        table.drop(connection, checkfirst=True)
