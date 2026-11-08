"""0009：模板逻辑删除和配置创建幂等；冻结结构。"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    ForeignKeyConstraint,
    MetaData,
    String,
    Table,
    text,
)
from sqlalchemy.dialects.mysql import VARBINARY

from app.adapters.assistant_schema_v8 import metadata as previous
from app.adapters.auth_schema_v1 import digest_type, utc_timestamp

metadata = MetaData()
for table in previous.sorted_tables:
    table.to_metadata(metadata)
templates = metadata.tables["prompt_templates"]
templates.append_column(
    Column("deleted", Boolean, nullable=False, server_default=text("0"))
)
config_requests = Table(
    "ai_configuration_requests",
    metadata,
    Column("class_id", String(36), primary_key=True),
    Column("actor_id", String(36), primary_key=True),
    Column("resource_type", String(12), primary_key=True),
    Column("request_key", VARBINARY(64), primary_key=True),
    Column("fingerprint", digest_type, nullable=False),
    Column("resource_id", String(36), nullable=False),
    Column("created_at", utc_timestamp, nullable=False),
    Column("expires_at", utc_timestamp, nullable=False, index=True),
    ForeignKeyConstraint(
        ["class_id", "actor_id"],
        ["accounts.class_id", "accounts.id"],
        name="fk_config_requests_actor",
    ),
    CheckConstraint(
        "resource_type IN ('template','assistant')", name="ck_config_requests_type"
    ),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
)
