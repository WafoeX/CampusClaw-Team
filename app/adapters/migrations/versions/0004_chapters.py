from alembic import op
from sqlalchemy import (
    JSON,
    Column,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import VARBINARY

from app.adapters.auth_schema_v1 import digest_type, utc_timestamp

revision = "0004_chapters"
down_revision = "0003_request_limits"


def upgrade():
    op.create_table(
        "chapters",
        Column("id", String(36), primary_key=True),
        Column("class_id", String(36), ForeignKey("classes.id"), nullable=False),
        Column("creator_id", String(36), ForeignKey("accounts.id"), nullable=False),
        Column("name", String(120), nullable=False),
        Column("sort_order", Integer, nullable=False),
        Column("revision", Integer, nullable=False),
        Column("created_at", utc_timestamp, nullable=False),
        Column("updated_at", utc_timestamp, nullable=False),
        UniqueConstraint("class_id", "id", name="uq_chapters_class_id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index(
        "ix_chapters_class_order_id", "chapters", ["class_id", "sort_order", "id"]
    )
    op.add_column("materials", Column("chapter_id", String(36), nullable=True))
    op.create_index(
        "ix_materials_class_chapter_order_id",
        "materials",
        ["class_id", "chapter_id", "sort_order", "id"],
    )
    op.create_foreign_key(
        "fk_materials_chapter_class",
        "materials",
        "chapters",
        ["class_id", "chapter_id"],
        ["class_id", "id"],
    )
    op.create_table(
        "chapter_idempotency",
        Column("class_id", String(36), ForeignKey("classes.id"), primary_key=True),
        Column("actor_id", String(36), ForeignKey("accounts.id"), primary_key=True),
        Column("method", String(6), primary_key=True),
        Column("resource_id", String(36), primary_key=True),
        Column("request_key", VARBINARY(64), primary_key=True),
        Column("fingerprint", digest_type, nullable=False),
        Column("result", JSON, nullable=False),
        Column("expires_at", utc_timestamp, nullable=False),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index(
        "ix_chapter_idempotency_expires_at", "chapter_idempotency", ["expires_at"]
    )


def downgrade():
    op.drop_index("ix_chapter_idempotency_expires_at", table_name="chapter_idempotency")
    op.drop_table("chapter_idempotency")
    op.drop_constraint("fk_materials_chapter_class", "materials", type_="foreignkey")
    op.drop_index("ix_materials_class_chapter_order_id", table_name="materials")
    op.drop_column("materials", "chapter_id")
    op.drop_index("ix_chapters_class_order_id", table_name="chapters")
    op.drop_table("chapters")
