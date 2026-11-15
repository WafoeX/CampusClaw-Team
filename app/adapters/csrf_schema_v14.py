from sqlalchemy import Column, ForeignKey, Index, MetaData, String, Table

from app.adapters.auth_schema_v1 import auth_sessions, digest_type, utc_timestamp

metadata = MetaData()
auth_sessions.to_metadata(metadata)

csrf_tokens = Table(
    "csrf_tokens",
    metadata,
    Column("digest", digest_type, primary_key=True),
    Column(
        "session_digest",
        digest_type,
        ForeignKey("auth_sessions.token_digest", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("action", String(32), nullable=False),
    Column("expires_at", utc_timestamp, nullable=False),
    Index("ix_csrf_tokens_expires_at", "expires_at"),
    mysql_engine="InnoDB",
)
