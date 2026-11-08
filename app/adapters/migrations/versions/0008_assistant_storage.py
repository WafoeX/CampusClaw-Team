"""仅扩展第 5 课存储；应用回退保留表，物理降级限合成隔离库。"""

from alembic import op
from sqlalchemy import inspect

from app.adapters.assistant_schema_v8 import TABLES

revision = "0008_assistant_storage"
down_revision = "0007_index_cleanup"


def upgrade():
    connection = op.get_bind()
    indexes = inspect(connection).get_indexes("accounts")
    if not any(index["name"] == "uq_accounts_class_id" for index in indexes):
        op.create_index(
            "uq_accounts_class_id", "accounts", ["class_id", "id"], unique=True
        )
    for table in TABLES:
        table.create(connection, checkfirst=True)


def downgrade():
    connection = op.get_bind()
    if not connection.engine.url.database.startswith("campusclaw_test_"):
        raise ValueError("第 5 课物理降级仅允许合成隔离库")
    for table in reversed(TABLES):
        table.drop(connection, checkfirst=True)
    # InnoDB 可用新组合索引替换 accounts→classes 的自动索引。
    # 物理回退先补回原 FK 支撑索引，再移除本版本组合索引。
    indexes = inspect(connection).get_indexes("accounts")
    if not any(
        index["name"] != "uq_accounts_class_id"
        and index["column_names"][:1] == ["class_id"]
        for index in indexes
    ):
        op.create_index("class_id", "accounts", ["class_id"])
    if any(
        index["name"] == "uq_accounts_class_id"
        for index in inspect(connection).get_indexes("accounts")
    ):
        op.drop_index("uq_accounts_class_id", table_name="accounts")
