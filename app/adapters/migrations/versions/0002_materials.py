from alembic import op

from app.adapters.material_schema_v2 import metadata

revision = "0002_materials"
down_revision = "0001_auth"


def upgrade():
    metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade():
    metadata.drop_all(bind=op.get_bind(), checkfirst=True)
