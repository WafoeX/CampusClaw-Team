from alembic import op
from sqlalchemy import Boolean, Column, inspect, text

from app.adapters.assistant_schema_v9 import config_requests

revision = "0009_app_configuration"
down_revision = "0008_assistant_storage"


def upgrade():
    connection = op.get_bind()
    if "deleted" not in {
        column["name"] for column in inspect(connection).get_columns("prompt_templates")
    }:
        op.add_column(
            "prompt_templates",
            Column("deleted", Boolean, nullable=False, server_default=text("0")),
        )
    config_requests.create(connection, checkfirst=True)


def downgrade():
    connection = op.get_bind()
    if not connection.engine.url.database.startswith("campusclaw_test_"):
        raise ValueError("只允许在合成隔离库物理降级")
    config_requests.drop(connection, checkfirst=True)
    if "deleted" in {
        column["name"] for column in inspect(connection).get_columns("prompt_templates")
    }:
        op.drop_column("prompt_templates", "deleted")
