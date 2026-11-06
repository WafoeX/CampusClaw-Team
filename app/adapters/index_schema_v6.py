"""0006 构建幂等记录；冻结结构，后续迁移另增版本。"""

from sqlalchemy import Column, ForeignKey, MetaData, String, Table
from sqlalchemy.dialects.mysql import VARBINARY

from app.adapters.auth_schema_v1 import accounts, classes, digest_type, utc_timestamp

metadata = MetaData()
classes.to_metadata(metadata)
accounts.to_metadata(metadata)
operations = Table(
    "material_index_operations",
    metadata,
    Column("class_id", String(36), ForeignKey("classes.id"), primary_key=True),
    Column("actor_id", String(36), ForeignKey("accounts.id"), primary_key=True),
    Column("material_id", String(36), primary_key=True),
    Column("request_key", VARBINARY(64), primary_key=True),
    Column("fingerprint", digest_type, nullable=False),
    Column("build_id", String(36), nullable=False),
    Column("expires_at", utc_timestamp, nullable=False, index=True),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
)
