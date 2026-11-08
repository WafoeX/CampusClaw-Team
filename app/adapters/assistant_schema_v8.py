"""0008 冻结结构：班级配置、私有轮次与出处；后续变更另增迁移。"""

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    Computed,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import VARBINARY

from app.adapters.auth_schema_v1 import digest_type, utc_timestamp
from app.adapters.index_schema_v5 import metadata as upstream_metadata

metadata = MetaData()
for upstream in upstream_metadata.sorted_tables:
    upstream.to_metadata(metadata)
accounts = metadata.tables["accounts"]
accounts.append_constraint(
    UniqueConstraint("class_id", "id", name="uq_accounts_class_id")
)
OPTIONS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}
APP_KEYS = "'polish', 'learning_plan', 'practice', 'material_qa'"


def ownership():
    return [
        Column("id", String(36), primary_key=True),
        Column("class_id", String(36), nullable=False),
        Column("creator_id", String(36), nullable=False),
        Column("name", String(64), nullable=False),
        Column("revision", Integer, nullable=False),
        Column("enabled", Boolean, nullable=False),
        Column("created_at", utc_timestamp, nullable=False),
        Column("updated_at", utc_timestamp, nullable=False),
    ]


def owned_config(name, *extra):
    return Table(
        name,
        metadata,
        *ownership(),
        *extra,
        UniqueConstraint("class_id", "id", name=f"uq_{name}_class_id"),
        ForeignKeyConstraint(
            ["class_id", "creator_id"],
            ["accounts.class_id", "accounts.id"],
            name=f"fk_{name}_creator",
        ),
        CheckConstraint("revision >= 1", name=f"ck_{name}_revision"),
        CheckConstraint("CHAR_LENGTH(name) BETWEEN 1 AND 64", name=f"ck_{name}_name"),
        Index(f"ix_{name}_class_updated", "class_id", "updated_at", "id"),
        **OPTIONS,
    )


templates = owned_config(
    "prompt_templates",
    Column("app_key", String(20), nullable=False),
    CheckConstraint(f"app_key IN ({APP_KEYS})", name="ck_templates_app"),
)
assistants = owned_config("assistants")
skills = owned_config(
    "skills",
    Column("name_key", VARBINARY(768), nullable=False),
    Column("builtin_key", String(24), nullable=True),
    UniqueConstraint("class_id", "name_key", name="uq_skills_name"),
    UniqueConstraint("class_id", "builtin_key", name="uq_skills_builtin"),
    CheckConstraint(
        "builtin_key IS NULL OR builtin_key IN ('problem_guidance','learning_plan')",
        name="ck_skills_builtin",
    ),
)


def config_revisions(name, parent, key, payload):
    return Table(
        name,
        metadata,
        Column("class_id", String(36), primary_key=True),
        Column(key, String(36), primary_key=True),
        Column("revision", Integer, primary_key=True),
        Column("creator_id", String(36), nullable=False),
        payload,
        Column("created_at", utc_timestamp, nullable=False),
        ForeignKeyConstraint(
            ["class_id", key],
            [f"{parent}.class_id", f"{parent}.id"],
            name=f"fk_{name}_parent",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["class_id", "creator_id"],
            ["accounts.class_id", "accounts.id"],
            name=f"fk_{name}_creator",
        ),
        CheckConstraint("revision >= 1", name=f"ck_{name}_revision"),
        *(
            [CheckConstraint("CHAR_LENGTH(prompt) <= 2000", name=f"ck_{name}_prompt")]
            if payload.name == "prompt"
            else []
        ),
        **OPTIONS,
    )


template_revisions = config_revisions(
    "prompt_template_revisions",
    "prompt_templates",
    "template_id",
    Column("prompt", Text, nullable=False),
)
assistant_revisions = config_revisions(
    "assistant_revisions",
    "assistants",
    "assistant_id",
    Column("prompt", Text, nullable=False),
)
skill_revisions = config_revisions(
    "skill_revisions",
    "skills",
    "skill_id",
    Column("definition", JSON, nullable=False),
)


def bindings(name, target, key):
    return Table(
        name,
        metadata,
        Column("class_id", String(36), primary_key=True),
        Column("assistant_id", String(36), primary_key=True),
        Column("revision", Integer, primary_key=True),
        Column(key, String(36), primary_key=True),
        ForeignKeyConstraint(
            ["class_id", "assistant_id", "revision"],
            [
                "assistant_revisions.class_id",
                "assistant_revisions.assistant_id",
                "assistant_revisions.revision",
            ],
            name=f"fk_{name}_revision",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["class_id", key],
            [f"{target}.class_id", f"{target}.id"],
            name=f"fk_{name}_target",
            ondelete="CASCADE",
        ),
        **OPTIONS,
    )


assistant_materials = bindings("assistant_materials", "materials", "material_id")
assistant_skills = bindings("assistant_skills", "skills", "skill_id")


def private_columns():
    return [
        Column("class_id", String(36), nullable=False),
        Column("owner_id", String(36), nullable=False),
    ]


def owner_fk(name):
    return ForeignKeyConstraint(
        ["class_id", "owner_id"],
        ["accounts.class_id", "accounts.id"],
        name=name,
    )


def session_fk(name):
    return ForeignKeyConstraint(
        ["class_id", "owner_id", "session_id"],
        ["sessions.class_id", "sessions.owner_id", "sessions.id"],
        name=name,
    )


def operation_fk(name, *, with_session=False):
    keys = ["class_id", "owner_id"] + (["session_id"] if with_session else [])
    return ForeignKeyConstraint(
        keys + ["operation_id"],
        [f"ai_operations.{k}" for k in keys] + ["ai_operations.id"],
        name=name,
    )


def message_fk(name):
    return ForeignKeyConstraint(
        ["class_id", "owner_id", "session_id", "message_id"],
        [
            "messages.class_id",
            "messages.owner_id",
            "messages.session_id",
            "messages.id",
        ],
        name=name,
    )


sessions = Table(
    "sessions",
    metadata,
    Column("id", String(36), primary_key=True),
    *private_columns(),
    Column("assistant_id", String(36), nullable=False),
    Column("mode", String(20), nullable=False),
    Column("created_at", utc_timestamp, nullable=False),
    Column("updated_at", utc_timestamp, nullable=False),
    Column("expires_at", utc_timestamp, nullable=False),
    owner_fk("fk_sessions_owner"),
    ForeignKeyConstraint(
        ["class_id", "assistant_id"],
        ["assistants.class_id", "assistants.id"],
        name="fk_sessions_assistant",
    ),
    UniqueConstraint("class_id", "owner_id", "id", name="uq_sessions_owner_id"),
    CheckConstraint(
        "mode IN ('material_qa','problem_guidance')", name="ck_sessions_mode"
    ),
    Index("ix_sessions_owner_updated", "class_id", "owner_id", "updated_at", "id"),
    **OPTIONS,
)
operations = Table(
    "ai_operations",
    metadata,
    Column("id", String(36), primary_key=True),
    *private_columns(),
    Column("session_id", String(36)),
    Column("app_key", String(20), nullable=False),
    Column("operation_scope", VARBINARY(64), nullable=False),
    Column("request_key", VARBINARY(64), nullable=False),
    Column("fingerprint", digest_type, nullable=False),
    Column("input_payload", JSON(none_as_null=True)),
    Column("status", String(16), nullable=False),
    Column("attempt_count", Integer, nullable=False),
    Column("lease_token", String(36)),
    Column("lease_expires_at", utc_timestamp),
    Column("created_at", utc_timestamp, nullable=False),
    Column("updated_at", utc_timestamp, nullable=False),
    Column("expires_at", utc_timestamp, nullable=False),
    Column(
        "active_session_id",
        String(36),
        Computed(
            "CASE WHEN status = 'running' THEN session_id ELSE NULL END", persisted=True
        ),
    ),
    owner_fk("fk_operations_owner"),
    session_fk("fk_operations_session"),
    UniqueConstraint("class_id", "owner_id", "id", name="uq_operations_owner_id"),
    UniqueConstraint(
        "class_id", "owner_id", "session_id", "id", name="uq_operations_session_id"
    ),
    UniqueConstraint(
        "class_id",
        "owner_id",
        "operation_scope",
        "request_key",
        name="uq_operations_key",
    ),
    UniqueConstraint(
        "class_id", "owner_id", "active_session_id", name="uq_operations_active"
    ),
    CheckConstraint(
        f"app_key IN ({APP_KEYS},'problem_guidance')", name="ck_operations_app"
    ),
    CheckConstraint("attempt_count BETWEEN 1 AND 3", name="ck_operations_attempts"),
    CheckConstraint(
        "OCTET_LENGTH(request_key) BETWEEN 1 AND 64", name="ck_operations_key"
    ),
    CheckConstraint(
        "status IN ('running','succeeded','failed','interrupted','revoked')",
        name="ck_operations_status",
    ),
    CheckConstraint(
        "(status = 'running' AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL) OR "
        "(status <> 'running' AND lease_token IS NULL AND lease_expires_at IS NULL)",
        name="ck_operations_lease",
    ),
    CheckConstraint(
        "(session_id IS NOT NULL AND operation_scope = CAST(session_id AS BINARY) "
        "AND app_key IN ('material_qa','problem_guidance')) OR "
        "(session_id IS NULL AND operation_scope = CAST(app_key AS BINARY) "
        "AND app_key IN ('polish','learning_plan','practice'))",
        name="ck_operations_scope",
    ),
    Index("ix_operations_lease", "status", "lease_expires_at"),
    Index("ix_operations_expiry", "expires_at"),
    **OPTIONS,
)
messages = Table(
    "messages",
    metadata,
    Column("id", String(36), primary_key=True),
    *private_columns(),
    Column("session_id", String(36), nullable=False),
    Column("operation_id", String(36), nullable=False),
    Column("role", String(9), nullable=False),
    Column("content", Text),
    Column("content_state", String(12), nullable=False),
    Column("created_at", utc_timestamp, nullable=False),
    Column("expires_at", utc_timestamp, nullable=False),
    operation_fk("fk_messages_operation", with_session=True),
    UniqueConstraint(
        "class_id", "owner_id", "session_id", "id", name="uq_messages_owner_id"
    ),
    UniqueConstraint("operation_id", "role", name="uq_messages_role"),
    CheckConstraint("role IN ('user','assistant')", name="ck_messages_role"),
    CheckConstraint(
        "(content_state = 'available' AND content IS NOT NULL) OR "
        "(content_state IN ('revoked','expired') AND content IS NULL)",
        name="ck_messages_content",
    ),
    Index(
        "ix_messages_session_created",
        "class_id",
        "owner_id",
        "session_id",
        "created_at",
        "id",
    ),
    **OPTIONS,
)
runs = Table(
    "application_runs",
    metadata,
    Column("id", String(36), primary_key=True),
    *private_columns(),
    Column("operation_id", String(36), nullable=False),
    Column("attempt", Integer, nullable=False),
    Column("status", String(16), nullable=False),
    Column("configuration", JSON, nullable=False),
    Column("details", JSON(none_as_null=True)),
    Column("error_code", Integer),
    Column("duration_ms", Integer),
    Column("created_at", utc_timestamp, nullable=False),
    Column("updated_at", utc_timestamp, nullable=False),
    Column("expires_at", utc_timestamp, nullable=False),
    Column(
        "successful_operation_id",
        String(36),
        Computed(
            "CASE WHEN status IN ('succeeded','revoked') THEN operation_id ELSE NULL END",
            persisted=True,
        ),
    ),
    operation_fk("fk_runs_operation"),
    UniqueConstraint("operation_id", "attempt", name="uq_runs_attempt"),
    UniqueConstraint("successful_operation_id", name="uq_runs_success"),
    CheckConstraint("attempt BETWEEN 1 AND 3", name="ck_runs_attempt"),
    CheckConstraint(
        "status IN ('running','succeeded','failed','interrupted','revoked')",
        name="ck_runs_status",
    ),
    CheckConstraint("status = 'succeeded' OR details IS NULL", name="ck_runs_details"),
    CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="ck_runs_duration"),
    Index("ix_runs_owner_updated", "class_id", "owner_id", "updated_at", "id"),
    **OPTIONS,
)
citations = Table(
    "message_citations",
    metadata,
    *private_columns(),
    Column("session_id", String(36), nullable=False),
    Column("message_id", String(36), primary_key=True),
    Column("ordinal", Integer, primary_key=True),
    Column("material_id", String(36), nullable=False),
    Column("source_version", Integer, nullable=False),
    Column("index_version", Integer, nullable=False),
    Column("index_config_version", String(64), nullable=False),
    Column("start_offset", Integer, nullable=False),
    Column("end_offset", Integer, nullable=False),
    Column("title", String(120)),
    Column("excerpt", Text),
    Column("status", String(12), nullable=False),
    Column("created_at", utc_timestamp, nullable=False),
    Column("expires_at", utc_timestamp, nullable=False),
    message_fk("fk_citations_message"),
    CheckConstraint("ordinal BETWEEN 1 AND 4", name="ck_citations_ordinal"),
    CheckConstraint(
        "start_offset >= 0 AND end_offset > start_offset", name="ck_citations_offsets"
    ),
    CheckConstraint(
        "source_version >= 1 AND index_version >= 1", name="ck_citations_version"
    ),
    CheckConstraint(
        "(status = 'available' AND title IS NOT NULL AND excerpt IS NOT NULL "
        "AND CHAR_LENGTH(excerpt) = end_offset - start_offset) OR "
        "(status IN ('deleted','revoked','expired') AND title IS NULL AND excerpt IS NULL)",
        name="ck_citations_content",
    ),
    Index("ix_citations_material", "material_id", "message_id"),
    **OPTIONS,
)
feedback = Table(
    "teaching_feedback",
    metadata,
    Column("id", String(36), primary_key=True),
    *private_columns(),
    Column("session_id", String(36), nullable=False),
    Column("message_id", String(36), nullable=False),
    Column("chapter_id", String(36)),
    Column("rating", String(12), nullable=False),
    Column("note", Text),
    Column("status", String(12), nullable=False),
    Column("revision", Integer, nullable=False),
    Column("creator_id", String(36), nullable=False),
    Column("created_at", utc_timestamp, nullable=False),
    Column("updated_at", utc_timestamp, nullable=False),
    Column("expires_at", utc_timestamp, nullable=False),
    message_fk("fk_feedback_message"),
    ForeignKeyConstraint(
        ["class_id", "chapter_id"],
        ["chapters.class_id", "chapters.id"],
        name="fk_feedback_chapter",
    ),
    CheckConstraint("creator_id = owner_id", name="ck_feedback_creator"),
    UniqueConstraint("message_id", name="uq_feedback_message"),
    CheckConstraint("rating IN ('helpful','unresolved')", name="ck_feedback_rating"),
    CheckConstraint(
        "status IN ('pending','handled','unavailable')", name="ck_feedback_status"
    ),
    CheckConstraint("revision >= 1", name="ck_feedback_revision"),
    CheckConstraint(
        "note IS NULL OR CHAR_LENGTH(note) <= 500", name="ck_feedback_note_length"
    ),
    CheckConstraint(
        "status = 'unavailable' OR rating = 'helpful' OR "
        "(note IS NOT NULL AND CHAR_LENGTH(TRIM(note)) BETWEEN 1 AND 500)",
        name="ck_feedback_note",
    ),
    Index(
        "ix_feedback_class_status", "class_id", "rating", "status", "updated_at", "id"
    ),
    **OPTIONS,
)
audits = Table(
    "ai_configuration_audits",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("class_id", String(36), nullable=False),
    Column("actor_id", String(36), nullable=False),
    Column("resource_type", String(16), nullable=False),
    Column("resource_id", String(36), nullable=False),
    Column("revision", Integer, nullable=False),
    Column("event", String(8), nullable=False),
    Column("created_at", utc_timestamp, nullable=False),
    CheckConstraint(
        "resource_type IN ('template','assistant','skill','feedback')",
        name="ck_ai_audits_type",
    ),
    CheckConstraint(
        "event IN ('create','update','disable','delete','handle')",
        name="ck_ai_audits_event",
    ),
    Index("ix_ai_audits_created", "created_at"),
    **OPTIONS,
)
TABLES = (
    templates,
    assistants,
    skills,
    template_revisions,
    assistant_revisions,
    skill_revisions,
    assistant_materials,
    assistant_skills,
    sessions,
    operations,
    messages,
    runs,
    citations,
    feedback,
    audits,
)
