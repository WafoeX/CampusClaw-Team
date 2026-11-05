"""0005 固定结构；未来结构变更另建版本，不改本文件。"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    text,
)

from app.adapters.auth_schema_v1 import utc_timestamp
from app.adapters.chapter_schema_v4 import metadata as chapter_metadata

metadata = MetaData()
for table in chapter_metadata.sorted_tables:
    table.to_metadata(metadata)
materials = metadata.tables["materials"]
materials.append_column(Column("active_index_version", Integer, nullable=True))
materials.append_column(Column("desired_index_version", Integer, nullable=True))
materials.append_column(
    Column("vector_ready", Boolean, nullable=False, server_default=text("0"))
)
materials.append_constraint(
    UniqueConstraint("class_id", "id", name="uq_materials_class_id")
)
options = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}

builds = Table(
    "material_index_builds",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("class_id", String(36), nullable=False),
    Column("material_id", String(36), nullable=False),
    Column("creator_id", String(36), ForeignKey("accounts.id"), nullable=False),
    Column("source_version", Integer, nullable=False),
    Column("index_version", Integer, nullable=False),
    Column("index_config_version", String(64), nullable=False),
    Column("mode", String(8), nullable=False),
    Column("window_size", Integer, nullable=False),
    Column("overlap", Integer, nullable=False),
    Column("status", String(16), nullable=False),
    Column("stage", String(32), nullable=False),
    Column("lease_expires_at", utc_timestamp, nullable=True),
    Column("created_at", utc_timestamp, nullable=False),
    Column("updated_at", utc_timestamp, nullable=False),
    ForeignKeyConstraint(
        ["class_id", "material_id"],
        ["materials.class_id", "materials.id"],
        name="fk_build_material_class",
    ),
    UniqueConstraint(
        "class_id", "material_id", "index_version", name="uq_build_material_version"
    ),
    UniqueConstraint(
        "class_id",
        "material_id",
        "source_version",
        "index_version",
        "index_config_version",
        name="uq_build_scope",
    ),
    CheckConstraint(
        "source_version > 0 AND index_version > 0", name="ck_build_versions"
    ),
    CheckConstraint(
        "status IN ('pending','building','published','keyword_only','failed','superseded')",
        name="ck_build_status",
    ),
    CheckConstraint("mode IN ('auto','custom','title')", name="ck_build_mode"),
    CheckConstraint(
        "window_size BETWEEN 100 AND 1200 AND overlap BETWEEN 0 AND 200 AND overlap < window_size",
        name="ck_build_window",
    ),
    Index("ix_build_class_status_lease", "class_id", "status", "lease_expires_at"),
    **options,
)

chunks = Table(
    "material_chunks",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("class_id", String(36), nullable=False),
    Column("material_id", String(36), nullable=False),
    Column("source_version", Integer, nullable=False),
    Column("index_version", Integer, nullable=False),
    Column("index_config_version", String(64), nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("start_offset", Integer, nullable=False),
    Column("end_offset", Integer, nullable=False),
    Column("content", String(1200), nullable=False),
    ForeignKeyConstraint(
        [
            "class_id",
            "material_id",
            "source_version",
            "index_version",
            "index_config_version",
        ],
        [
            "material_index_builds.class_id",
            "material_index_builds.material_id",
            "material_index_builds.source_version",
            "material_index_builds.index_version",
            "material_index_builds.index_config_version",
        ],
        name="fk_chunk_build_scope",
    ),
    UniqueConstraint(
        "class_id",
        "material_id",
        "index_version",
        "ordinal",
        name="uq_chunk_version_ordinal",
    ),
    CheckConstraint(
        "ordinal BETWEEN 0 AND 63 AND start_offset >= 0 AND end_offset > start_offset AND end_offset <= 32000 AND end_offset - start_offset = CHAR_LENGTH(content)",
        name="ck_chunk_offsets",
    ),
    Index(
        "ft_chunks_content",
        "content",
        mysql_prefix="FULLTEXT",
        mysql_with_parser="ngram",
    ),
    **options,
)

cleanups = Table(
    "material_index_cleanups",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("class_id", String(36), nullable=False),
    Column("material_id", String(36), nullable=False),
    Column("source_version", Integer, nullable=False),
    Column("index_version", Integer, nullable=False),
    Column("index_config_version", String(64), nullable=False),
    Column("scope_key", String(64), nullable=False, unique=True),
    Column("status", String(16), nullable=False),
    Column("attempts", Integer, nullable=False, server_default=text("0")),
    Column("next_attempt_at", utc_timestamp, nullable=True),
    Column("created_at", utc_timestamp, nullable=False),
    Column("updated_at", utc_timestamp, nullable=False),
    CheckConstraint(
        "status IN ('pending','retry','complete','manual') AND attempts BETWEEN 0 AND 3",
        name="ck_cleanup_state",
    ),
    Index("ix_cleanup_status_next", "status", "next_attempt_at"),
    **options,
)

INDEX_TABLES = (builds, chunks, cleanups)
