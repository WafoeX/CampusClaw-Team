from sqlalchemy import Column, Index, Integer, MetaData, Table

from app.adapters.auth_schema_v1 import digest_type, utc_timestamp

metadata = MetaData()
request_limits = Table(
    "request_limits",
    metadata,
    Column("scope_digest", digest_type, primary_key=True),
    Column("window_start", utc_timestamp, primary_key=True),
    Column("request_count", Integer, nullable=False),
    Index("ix_request_limits_window", "window_start"),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
)
