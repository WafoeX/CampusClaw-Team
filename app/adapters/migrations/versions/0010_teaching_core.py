"""人工题库、不可变测验和规则评分的只增迁移。"""

from alembic import op
from sqlalchemy import inspect

from app.adapters.teaching_schema_v10 import TABLES

revision = "0010_teaching_core"
down_revision = "0009_app_configuration"


def upgrade():
    connection = op.get_bind()
    if not any(
        index["name"] == "uq_materials_class_id"
        for index in inspect(connection).get_indexes("materials")
    ):
        op.create_index(
            "uq_materials_class_id", "materials", ["class_id", "id"], unique=True
        )
    for table in TABLES:
        table.create(connection, checkfirst=True)


def downgrade():
    connection = op.get_bind()
    if not connection.engine.url.database.startswith("campusclaw_test_"):
        raise ValueError("只允许在合成隔离库物理降级教学数据")
    for table in reversed(TABLES):
        table.drop(connection, checkfirst=True)
    # 既有资料外键也可能选用此索引；回退教学表时保留扩展索引。
