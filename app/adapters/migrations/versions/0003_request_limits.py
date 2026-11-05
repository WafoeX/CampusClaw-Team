from alembic import op

from app.adapters.rate_limit_schema_v3 import metadata

revision = "0003_request_limits"
down_revision = "0002_materials"


def upgrade():
    metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade():
    metadata.drop_all(bind=op.get_bind(), checkfirst=True)
