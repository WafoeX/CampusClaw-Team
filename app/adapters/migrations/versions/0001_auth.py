from alembic import op

from app.adapters.auth_schema_v1 import metadata

revision = "0001_auth"
down_revision = None


def upgrade():
    metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade():
    metadata.drop_all(bind=op.get_bind(), checkfirst=True)
