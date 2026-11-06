from alembic import op
from sqlalchemy import Column, String, inspect

from app.adapters.index_schema_v7 import tombstones

revision = "0007_index_cleanup"
down_revision = "0006_index_operations"


def upgrade():
    connection = op.get_bind()
    for name in ("material_index_builds", "material_index_cleanups"):
        columns = {column["name"] for column in inspect(connection).get_columns(name)}
        if "vector_collection" not in columns:
            op.add_column(name, Column("vector_collection", String(80), nullable=True))
    tombstones.create(connection, checkfirst=True)


def downgrade():
    tombstones.drop(op.get_bind(), checkfirst=True)
    for name in ("material_index_builds", "material_index_cleanups"):
        op.drop_column(name, "vector_collection")
