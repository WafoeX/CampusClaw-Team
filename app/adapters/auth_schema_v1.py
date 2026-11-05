from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    LargeBinary,
    MetaData,
    String,
    Table,
)
from sqlalchemy.dialects.mysql import BINARY, DATETIME
from sqlalchemy.types import DateTime

# 版本 1 迁移使用此结构。后续迁移须保留这一版本的定义。
metadata = MetaData()
utc_timestamp = DateTime().with_variant(DATETIME(fsp=6), "mysql")
digest_type = LargeBinary(32).with_variant(BINARY(32), "mysql")

classes = Table(
    "classes",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("code", String(64), nullable=False, unique=True),
    Column("name", String(120), nullable=False),
    Column("created_at", utc_timestamp, nullable=False),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
)

accounts = Table(
    "accounts",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("login_name", String(64), nullable=False, unique=True),
    Column("password_hash", String(255), nullable=False),
    Column("enabled", Boolean, nullable=False),
    Column("class_id", String(36), ForeignKey("classes.id"), nullable=False),
    Column("role", String(7), nullable=False),
    Column("created_at", utc_timestamp, nullable=False),
    Column("updated_at", utc_timestamp, nullable=False),
    CheckConstraint("role IN ('teacher', 'student')", name="ck_accounts_role"),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
)

auth_sessions = Table(
    "auth_sessions",
    metadata,
    Column("account_id", String(36), ForeignKey("accounts.id"), primary_key=True),
    Column("token_digest", digest_type, nullable=False, unique=True),
    Column("issued_at", utc_timestamp, nullable=False),
    Column("expires_at", utc_timestamp, nullable=False),
    Column("revoked_at", utc_timestamp),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
)

auth_audits = Table(
    "auth_audits",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("account_id", String(36), nullable=False),
    Column("event", String(20), nullable=False),
    Column("created_at", utc_timestamp, nullable=False, index=True),
    CheckConstraint(
        "event IN ('login', 'logout', 'disable', 'reset_password')",
        name="ck_auth_audits_event",
    ),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
)
