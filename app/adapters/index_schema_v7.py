"""0007 版本化向量清理目标和无正文出处映射。"""

from sqlalchemy import Column, Index, Integer, MetaData, String, Table

from app.adapters.auth_schema_v1 import utc_timestamp
from app.adapters.index_schema_v5 import metadata as base_metadata

metadata = MetaData()
for table in base_metadata.sorted_tables:
    table.to_metadata(metadata)
builds = metadata.tables["material_index_builds"]
cleanups = metadata.tables["material_index_cleanups"]
for table in (builds, cleanups):
    table.append_column(Column("vector_collection", String(80), nullable=True))
tombstones = Table(
    "material_chunk_tombstones",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("class_id", String(36), nullable=False),
    Column("material_id", String(36), nullable=False),
    Column("source_version", Integer, nullable=False),
    Column("index_version", Integer, nullable=False),
    Column("index_config_version", String(64), nullable=False),
    Column("created_at", utc_timestamp, nullable=False),
    Column("expires_at", utc_timestamp, nullable=False),
    Index("ix_tombstone_material", "class_id", "material_id"),
    Index("ix_tombstone_expiry", "expires_at"),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
)
