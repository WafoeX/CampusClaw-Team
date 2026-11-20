"""在一次性 MySQL 库验证 0016 的空库、旧行、重跑与隔离降级。"""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from alembic import command
from sqlalchemy import delete, func, insert, inspect, select, update
from sqlalchemy.exc import OperationalError
from werkzeug.security import generate_password_hash

from app.adapters.ai_repository import AIRepository
from app.adapters.auth_repository import AuthRepository
from app.adapters.auth_schema_v1 import accounts
from app.adapters.database import mysql_engine
from app.adapters.migrations.runner import migrate, migration_config
from app.adapters.operation_audit_schema_v13 import events
from app.adapters.teaching_schema_v12 import jobs
from app.config import Settings

settings = Settings.load(os.environ, Path("app/BUILD_VERSION"))
engine = mysql_engine(
    host=settings.mysql_host,
    port=settings.mysql_port,
    database=settings.mysql_database,
    user=settings.mysql_user,
    password=settings.mysql_password,
)
assert engine.url.database.startswith("campusclaw_test_")
migrate(engine)
assert {"total_tokens", "usage_status"} <= {
    item["name"] for item in inspect(engine).get_columns("teaching_jobs")
}
with engine.connect() as connection:
    assert connection.scalar(select(func.count()).select_from(jobs)) == 0
    assert connection.scalar(select(func.count()).select_from(events)) == 0

config = migration_config()
with engine.connect() as connection:
    config.attributes["connection"] = connection
    command.downgrade(config, "0015_quiz_list_index")
    connection.commit()
assert "usage_status" not in {
    item["name"] for item in inspect(engine).get_columns("teaching_jobs")
}

AuthRepository(engine).seed_demo_accounts(
    generate_password_hash(settings.mysql_password, method="scrypt")
)
with engine.connect() as connection:
    actor = connection.execute(select(accounts.c.id, accounts.c.class_id)).first()
assert actor is not None
now = datetime.now(UTC).replace(tzinfo=None)
job_id = str(uuid4())
audit_id = str(uuid4())
with engine.begin() as connection:
    connection.execute(
        insert(jobs).values(
            id=job_id,
            kind="candidate_questions",
            class_id=actor.class_id,
            creator_id=actor.id,
            state="failed",
            generation=1,
            attempt=1,
            input={},
            trace_id=str(uuid4()),
            event_id=str(uuid4()),
            available_at=now,
            created_at=now,
            updated_at=now,
        )
    )
    connection.execute(
        insert(events).values(
            id=audit_id,
            request_id=uuid4().hex,
            class_id=actor.class_id,
            actor_id=actor.id,
            created_at=now,
            action="legacy",
            resource_type="teaching_job",
            resource_id=job_id,
            outcome="succeeded",
            usage_status="not_applicable",
            duration_ms=1,
            event_json="{}",
            expires_at=now + timedelta(days=90),
        )
    )

migrate(engine)
migrate(engine)
inspector = inspect(engine)
assert "ix_operation_audit_class_resource" in {
    item["name"] for item in inspector.get_indexes("operation_audit_events")
}
assert "ck_teaching_job_usage" in {
    item["name"] for item in inspector.get_check_constraints("teaching_jobs")
}
with engine.connect() as connection:
    old = connection.execute(select(jobs).where(jobs.c.id == job_id)).first()._mapping
    assert old["state"] == "failed"
    assert old["total_tokens"] is None and old["usage_status"] is None
    assert (
        connection.scalar(select(events.c.outcome).where(events.c.id == audit_id))
        == "succeeded"
    )
    assert connection.scalar(select(func.count()).select_from(jobs)) == 1

try:
    with engine.begin() as connection:
        connection.execute(
            update(jobs)
            .where(jobs.c.id == job_id)
            .values(usage_status="measured", total_tokens=None)
        )
except OperationalError as error:
    assert error.orig.args[0] == 3819
else:
    raise AssertionError("无效用量组合未被 MySQL 拒绝")
with engine.begin() as connection:
    connection.execute(
        update(jobs)
        .where(jobs.c.id == job_id)
        .values(usage_status="measured", total_tokens=17)
    )
with engine.connect() as connection:
    assert (
        connection.scalar(select(jobs.c.total_tokens).where(jobs.c.id == job_id)) == 17
    )

expired_id = str(uuid4())
expired_row = dict(
    id=expired_id,
    request_id=uuid4().hex,
    class_id=actor.class_id,
    actor_id=actor.id,
    created_at=now - timedelta(days=91),
    action="terminal",
    resource_type="teaching_job",
    resource_id=job_id,
    outcome="failed",
    usage_status="unavailable",
    duration_ms=3,
    event_json="{}",
    expires_at=now - timedelta(days=1),
)
with engine.begin() as connection:
    connection.execute(insert(events).values(expired_row))
cleanup = AIRepository(engine)
assert cleanup.cleanup_expired(now)["operation_audit_expired"] == 1
with engine.begin() as connection:
    connection.execute(insert(events).values(expired_row))
assert cleanup.cleanup_expired(now)["operation_audit_expired"] == 1
with engine.connect() as connection:
    assert (
        connection.scalar(select(events.c.id).where(events.c.id == expired_id)) is None
    )

new_outcome = {**expired_row, "id": str(uuid4()), "request_id": uuid4().hex}
new_outcome["expires_at"] = now + timedelta(days=1)
with engine.begin() as connection:
    connection.execute(insert(events).values(new_outcome))
with engine.connect() as connection:
    config.attributes["connection"] = connection
    try:
        command.downgrade(config, "0015_quiz_list_index")
    except ValueError as error:
        assert "降级前须处理" in str(error)
    else:
        raise AssertionError("新终态审计存在时物理降级必须先拒绝")
assert "usage_status" in {
    item["name"] for item in inspect(engine).get_columns("teaching_jobs")
}
with engine.begin() as connection:
    connection.execute(delete(events).where(events.c.id == new_outcome["id"]))

with engine.connect() as connection:
    config.attributes["connection"] = connection
    command.downgrade(config, "0015_quiz_list_index")
    connection.commit()
assert "usage_status" not in {
    item["name"] for item in inspect(engine).get_columns("teaching_jobs")
}
migrate(engine)
with engine.connect() as connection:
    assert connection.scalar(select(func.count()).select_from(jobs)) == 1
    assert (
        connection.scalar(select(events.c.outcome).where(events.c.id == audit_id))
        == "succeeded"
    )
print("teaching_job_audit_migration_ok")
