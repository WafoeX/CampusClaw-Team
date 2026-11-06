"""跨存储去内容凭证；调用方负责同一个 MySQL 事务。"""

import json
from hashlib import sha256
from uuid import uuid4

from sqlalchemy.dialects.mysql import insert

from app.adapters.index_schema_v7 import cleanups


def record_cleanup(connection, row, now):
    fields = {
        key: row[key]
        for key in (
            "class_id",
            "material_id",
            "source_version",
            "index_version",
            "index_config_version",
        )
    }
    key = sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()
    statement = insert(cleanups).values(
        **fields,
        id=str(uuid4()),
        scope_key=key,
        status="pending",
        attempts=0,
        next_attempt_at=now,
        created_at=now,
        updated_at=now,
        vector_collection=row.get("vector_collection"),
    )
    connection.execute(
        statement.on_duplicate_key_update(
            status="pending",
            attempts=0,
            next_attempt_at=now,
            updated_at=now,
            vector_collection=row.get("vector_collection"),
        )
    )
