"""增加一次性配置写入令牌摘要。"""

from alembic import op

from app.adapters.csrf_schema_v14 import csrf_tokens

revision = "0014_csrf_tokens"
down_revision = "0013_operation_audit"


def upgrade():
    csrf_tokens.create(op.get_bind(), checkfirst=True)


def downgrade():
    connection = op.get_bind()
    if not connection.engine.url.database.startswith("campusclaw_test_"):
        raise ValueError("只允许在合成隔离库物理降级配置写入令牌")
    csrf_tokens.drop(connection, checkfirst=True)
