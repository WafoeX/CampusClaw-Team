"""在合成 MySQL 库核对 0011 的约束、回退、只增恢复与清理。"""

import os
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import insert, inspect, select, update
from sqlalchemy.exc import IntegrityError

from app.adapters.assistant_schema_v8 import accounts
from app.adapters.auth_schema_v1 import classes
from app.adapters.database import mysql_engine
from app.adapters.migrations.runner import migrate
from app.adapters.tool_audit import append_tool_result, cleanup_tool_audit
from app.adapters.tool_schema_v11 import (
    TABLES,
    approvals,
    attempts,
    connectors,
    discoveries,
    results,
)


def newid():
    return str(uuid4())


engine = mysql_engine(
    host=os.environ["MYSQL_HOST"],
    port=int(os.environ["MYSQL_PORT"]),
    database=os.environ["MYSQL_DATABASE"],
    user=os.environ["MYSQL_USER"],
    password=os.environ["MYSQL_PASSWORD"],
)
assert engine.url.database.startswith("campusclaw_test_")
now = datetime(2026, 11, 1)
names = {table.name for table in TABLES}
migrate(engine)
migrate(engine)
assert names <= set(inspect(engine).get_table_names())


def rejects(table, values):
    try:
        with engine.begin() as connection:
            connection.execute(insert(table).values(values))
    except IntegrityError:
        return
    raise AssertionError(f"约束未拒绝 {table.name}")


class_a, class_b, teacher_a, teacher_b = (newid() for _ in range(4))
with engine.begin() as connection:
    for class_id, teacher in ((class_a, teacher_a), (class_b, teacher_b)):
        connection.execute(
            insert(classes).values(
                id=class_id, code=class_id, name="合成班级", created_at=now
            )
        )
        connection.execute(
            insert(accounts).values(
                id=teacher,
                class_id=class_id,
                login_name=teacher,
                password_hash="synthetic-unusable",
                enabled=True,
                role="teacher",
                created_at=now,
                updated_at=now,
            )
        )

connector = dict(
    id=newid(),
    class_id=class_a,
    creator_id=teacher_a,
    alias="migration-check",
    directory_key="teaching",
    directory_version="v1",
    generation=1,
    status="connected",
    created_at=now,
    updated_at=now,
)
with engine.begin() as connection:
    connection.execute(insert(connectors).values(connector))
rejects(connectors, connector | {"id": newid()})
rejects(connectors, connector | {"id": newid(), "class_id": class_b})

definition = {"name": "formula_hint", "inputSchema": {"type": "object"}}
discovery = dict(
    class_id=class_a,
    connector_id=connector["id"],
    name="formula_hint",
    generation=1,
    fingerprint="f" * 64,
    definition=definition,
    approved=True,
    enabled=True,
)
rejects(discoveries, discovery | {"class_id": class_b})
approval = {key: value for key, value in discovery.items() if key != "approved"} | {
    "id": newid(),
    "teacher_id": teacher_a,
    "created_at": now,
}
rejects(approvals, approval | {"teacher_id": teacher_b})
with engine.begin() as connection:
    connection.execute(insert(discoveries).values(discovery))
    connection.execute(insert(approvals).values(approval))
rejects(discoveries, discovery)

attempt = dict(
    id=newid(),
    class_id=class_a,
    actor_id=teacher_a,
    session_id=newid(),
    run_id=newid(),
    connector_id=connector["id"],
    tool_name=discovery["name"],
    generation=1,
    fingerprint=discovery["fingerprint"],
    round_number=1,
    ordinal=1,
    send_permitted=True,
    request_id=newid(),
    created_at=now,
    recover_at=now + timedelta(seconds=40),
    expires_at=now + timedelta(days=90),
)
with engine.begin() as connection:
    connection.execute(insert(attempts).values(attempt))
    assert append_tool_result(
        connection,
        class_a,
        attempt["id"],
        outcome="succeeded",
        reason=None,
        duration_ms=12,
        now=now,
    )
    assert not append_tool_result(
        connection,
        class_a,
        attempt["id"],
        outcome="error",
        reason="interrupted",
        duration_ms=0,
        now=now,
    )
rejects(attempts, attempt | {"id": newid()})
rejects(attempts, attempt | {"id": newid(), "class_id": class_b})
rejects(
    results,
    dict(
        attempt_id=attempt["id"],
        class_id=class_b,
        outcome="succeeded",
        reason=None,
        duration_ms=12,
        created_at=now,
    ),
)

pending = attempt | {"id": newid(), "ordinal": 2}
with engine.begin() as connection:
    connection.execute(insert(attempts).values(pending))
    connection.execute(
        update(connectors)
        .where(connectors.c.id == connector["id"])
        .values(deleted_at=now, status="disconnected", generation=2)
    )
    assert cleanup_tool_audit(connection, now)["tool_audit_recovered"] == 0

recovery_time = now + timedelta(minutes=1)
with engine.begin() as connection:
    assert cleanup_tool_audit(connection, recovery_time)["tool_audit_recovered"] == 1
    assert cleanup_tool_audit(connection, recovery_time)["tool_audit_recovered"] == 0
    result = (
        connection.execute(select(results).where(results.c.attempt_id == pending["id"]))
        .mappings()
        .one()
    )
    assert result["outcome"] == "error" and result["reason"] == "interrupted"
    success = (
        connection.execute(select(results).where(results.c.attempt_id == attempt["id"]))
        .mappings()
        .one()
    )
    assert success["outcome"] == "succeeded"
    backup = [dict(success), dict(result)]
    assert {"definition", "payload", "arguments", "token"}.isdisjoint(
        attempts.c.keys() + results.c.keys()
    )

expiry = now + timedelta(days=90)
with engine.begin() as connection:
    assert cleanup_tool_audit(connection, expiry)["tool_audit_expired"] == 2
    assert (
        connection.execute(select(results).where(results.c.class_id == class_a)).all()
        == []
    )
    # 用清理前的合成行模拟还原，在恢复接流量前重放同一到期规则。
    connection.execute(insert(attempts), [attempt, pending])
    connection.execute(insert(results), backup)
    assert cleanup_tool_audit(connection, expiry)["tool_audit_expired"] == 2
    assert (
        connection.execute(select(results).where(results.c.class_id == class_a)).all()
        == []
    )

config = Config()
config.set_main_option(
    "script_location", str(Path("app/adapters/migrations").resolve())
)
with engine.connect() as connection:
    config.attributes["connection"] = connection
    command.downgrade(config, "0010_teaching_core")
    connection.commit()
assert not names & set(inspect(engine).get_table_names())
with engine.connect() as connection:
    assert (
        connection.scalar(select(accounts.c.class_id).where(accounts.c.id == teacher_a))
        == class_a
    )
    assert "quiz_results" in inspect(connection).get_table_names()
migrate(engine)
assert names <= set(inspect(engine).get_table_names())
print("受控工具迁移、约束、恢复与清理通过")
