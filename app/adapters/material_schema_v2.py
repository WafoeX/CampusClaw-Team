from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
)
from sqlalchemy.dialects.mysql import MEDIUMBLOB, VARBINARY

from app.adapters.auth_schema_v1 import accounts, classes, digest_type, utc_timestamp

metadata = MetaData()
options = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}

materials = Table(
    "materials",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("class_id", String(36), ForeignKey(classes.c.id), nullable=False),
    Column("creator_id", String(36), ForeignKey(accounts.c.id), nullable=False),
    Column("title", String(120), nullable=False),
    Column("sort_order", Integer, nullable=False),
    Column("source_format", String(8), nullable=False),
    Column("media_type", String(32), nullable=False),
    Column("byte_size", Integer, nullable=False),
    Column("character_count", Integer, nullable=False),
    Column("content_version", Integer, nullable=False),
    Column("revision", Integer, nullable=False),
    Column("created_at", utc_timestamp, nullable=False),
    Column("updated_at", utc_timestamp, nullable=False),
    Index("ix_materials_class_order_id", "class_id", "sort_order", "id"),
    **options,
)

bodies = Table(
    "material_bodies",
    metadata,
    Column("material_id", String(36), ForeignKey(materials.c.id), primary_key=True),
    Column(
        "content", LargeBinary().with_variant(MEDIUMBLOB(), "mysql"), nullable=False
    ),
    **options,
)

uploads = Table(
    "material_uploads",
    metadata,
    Column("class_id", String(36), ForeignKey(classes.c.id), primary_key=True),
    Column("creator_id", String(36), ForeignKey(accounts.c.id), primary_key=True),
    Column(
        "request_key",
        LargeBinary(64).with_variant(VARBINARY(64), "mysql"),
        primary_key=True,
    ),
    Column("fingerprint", digest_type, nullable=False),
    Column("material_id", String(36), nullable=False, index=True),
    Column("result", JSON, nullable=True),
    Column("deleted", Boolean, nullable=False),
    Column("expires_at", utc_timestamp, nullable=False, index=True),
    **options,
)

deletions = Table(
    "material_deletions",
    metadata,
    Column("material_id", String(36), primary_key=True),
    Column("deleted_at", utc_timestamp, nullable=False),
    **options,
)
