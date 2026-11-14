"""追加操作审计，不回填私人执行记录。"""

from alembic import op

from app.adapters.operation_audit_schema_v13 import events

revision = "0013_operation_audit"
down_revision = "0012_teaching_jobs"


def upgrade():
    events.create(op.get_bind(), checkfirst=True)


def downgrade():
    connection = op.get_bind()
    if not connection.engine.url.database.startswith("campusclaw_test_"):
        raise ValueError("只允许在合成隔离库物理降级操作审计")
    events.drop(connection, checkfirst=True)
