from alembic import op

from app.adapters.index_schema_v6 import operations

revision = "0006_index_operations"
down_revision = "0005_indexing"


def upgrade():
    operations.create(op.get_bind(), checkfirst=True)


def downgrade():
    operations.drop(op.get_bind(), checkfirst=True)
