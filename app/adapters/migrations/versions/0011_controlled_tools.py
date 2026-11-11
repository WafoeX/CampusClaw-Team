"""追加受控工具数据表，保留全部既有业务数据。"""

from alembic import op

from app.adapters.tool_schema_v11 import TABLES

revision = "0011_controlled_tools"
down_revision = "0010_teaching_core"


def upgrade():
    connection = op.get_bind()
    for table in TABLES:
        table.create(connection, checkfirst=True)


def downgrade():
    connection = op.get_bind()
    if not connection.engine.url.database.startswith("campusclaw_test_"):
        raise ValueError("只允许在合成隔离库物理降级受控工具数据")
    for table in reversed(TABLES):
        table.drop(connection, checkfirst=True)
