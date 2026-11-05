from alembic import op
from sqlalchemy import Boolean, Column, Integer, inspect, text

from app.adapters.index_schema_v5 import INDEX_TABLES

revision = "0005_indexing"
down_revision = "0004_chapters"


def upgrade():
    connection = op.get_bind()
    token_size, stopwords = connection.execute(
        text("SELECT @@ngram_token_size, @@innodb_ft_enable_stopword")
    ).one()
    if token_size != 2 or stopwords:
        raise ValueError(
            "索引迁移需要 ngram_token_size=2、innodb_ft_enable_stopword=OFF，请核对 MySQL 启动配置"
        )
    # MySQL DDL 自动提交，按实际已完成步骤恢复，不清库重跑。
    existing = {
        column["name"] for column in inspect(connection).get_columns("materials")
    }
    for column in (
        Column("active_index_version", Integer, nullable=True),
        Column("desired_index_version", Integer, nullable=True),
        Column("vector_ready", Boolean, nullable=False, server_default=text("0")),
    ):
        if column.name not in existing:
            op.add_column("materials", column)
    uniques = {
        entry["name"]
        for entry in inspect(connection).get_unique_constraints("materials")
    }
    if "uq_materials_class_id" not in uniques:
        op.create_unique_constraint(
            "uq_materials_class_id", "materials", ["class_id", "id"]
        )
    for table in INDEX_TABLES:
        table.create(connection, checkfirst=True)


def downgrade():
    connection = op.get_bind()
    for table in reversed(INDEX_TABLES):
        table.drop(connection, checkfirst=True)
    op.drop_constraint("uq_materials_class_id", "materials", type_="unique")
    for name in ("vector_ready", "desired_index_version", "active_index_version"):
        op.drop_column("materials", name)
