"""按班级提供测验列表的稳定分页顺序。"""

from alembic import op
from sqlalchemy import inspect

revision = "0015_quiz_list_index"
down_revision = "0014_csrf_tokens"
INDEX = "ix_quizzes_class_created_id"


def upgrade():
    connection = op.get_bind()
    if INDEX not in {
        index["name"] for index in inspect(connection).get_indexes("quizzes")
    }:
        connection.exec_driver_sql(
            "CREATE INDEX ix_quizzes_class_created_id "
            "ON quizzes (class_id, created_at DESC, id)"
        )


def downgrade():
    connection = op.get_bind()
    if not connection.engine.url.database.startswith("campusclaw_test_"):
        raise ValueError("只允许在合成隔离库物理降级测验分页索引")
    if INDEX in {index["name"] for index in inspect(connection).get_indexes("quizzes")}:
        op.drop_index(INDEX, table_name="quizzes")
