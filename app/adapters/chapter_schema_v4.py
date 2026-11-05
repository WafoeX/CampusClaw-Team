from sqlalchemy import (
    JSON,
    Column,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import VARBINARY

from app.adapters.auth_schema_v1 import accounts, classes, digest_type, utc_timestamp
from app.adapters.material_schema_v2 import materials as original_materials

metadata = MetaData()
classes.to_metadata(metadata)
accounts.to_metadata(metadata)
materials = original_materials.to_metadata(metadata)
materials.append_column(Column("chapter_id", String(36), nullable=True))

chapters = Table(
    "chapters",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("class_id", String(36), ForeignKey("classes.id"), nullable=False),
    Column("creator_id", String(36), ForeignKey("accounts.id"), nullable=False),
    Column("name", String(120), nullable=False),
    Column("sort_order", Integer, nullable=False),
    Column("revision", Integer, nullable=False),
    Column("created_at", utc_timestamp, nullable=False),
    Column("updated_at", utc_timestamp, nullable=False),
    UniqueConstraint("class_id", "id", name="uq_chapters_class_id"),
    Index("ix_chapters_class_order_id", "class_id", "sort_order", "id"),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
)

chapter_membership = ForeignKeyConstraint(
    [materials.c.class_id, materials.c.chapter_id],
    [chapters.c.class_id, chapters.c.id],
    name="fk_materials_chapter_class",
)
materials.append_constraint(chapter_membership)
Index(
    "ix_materials_class_chapter_order_id",
    materials.c.class_id,
    materials.c.chapter_id,
    materials.c.sort_order,
    materials.c.id,
)

chapter_idempotency = Table(
    "chapter_idempotency",
    metadata,
    Column("class_id", String(36), ForeignKey("classes.id"), primary_key=True),
    Column("actor_id", String(36), ForeignKey("accounts.id"), primary_key=True),
    Column("method", String(6), primary_key=True),
    Column("resource_id", String(36), primary_key=True),
    Column("request_key", VARBINARY(64), primary_key=True),
    Column("fingerprint", digest_type, nullable=False),
    Column("result", JSON, nullable=False),
    Column("expires_at", utc_timestamp, nullable=False, index=True),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
)
