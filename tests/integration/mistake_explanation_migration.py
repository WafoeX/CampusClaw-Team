"""在一次性 MySQL 库验证 0018 的空库、旧行、重跑与隔离降级。"""

import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from alembic import command
from sqlalchemy import delete, func, insert, inspect, select
from sqlalchemy.exc import OperationalError
from werkzeug.security import generate_password_hash

from app.adapters.assistant_schema_v8 import skills
from app.adapters.auth_repository import AuthRepository
from app.adapters.auth_schema_v1 import accounts
from app.adapters.database import mysql_engine
from app.adapters.migrations.runner import migrate, migration_config
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


def builtin_rule():
    return next(
        item["sqltext"]
        for item in inspect(engine).get_check_constraints("skills")
        if item["name"] == "ck_skills_builtin"
    )


assert "mistake_explanation" in builtin_rule()
with engine.connect() as connection:
    assert connection.scalar(select(func.count()).select_from(skills)) == 0

config = migration_config()
with engine.connect() as connection:
    config.attributes["connection"] = connection
    command.downgrade(config, "0017_teacher_score_override")
    connection.commit()
assert "mistake_explanation" not in builtin_rule()

AuthRepository(engine).seed_demo_accounts(
    generate_password_hash(settings.mysql_password, method="scrypt")
)
with engine.connect() as connection:
    actor = connection.execute(select(accounts.c.id, accounts.c.class_id)).first()
assert actor is not None
now = datetime.now(UTC).replace(tzinfo=None)
old_id, new_id = str(uuid4()), str(uuid4())


def skill_row(identifier, name, builtin):
    return dict(
        id=identifier,
        class_id=actor.class_id,
        creator_id=actor.id,
        name=name,
        revision=1,
        enabled=True,
        created_at=now,
        updated_at=now,
        name_key=name.encode(),
        builtin_key=builtin,
    )


with engine.begin() as connection:
    connection.execute(
        insert(skills).values(skill_row(old_id, "旧解题技能", "problem_guidance"))
    )
migrate(engine)
migrate(engine)
assert "mistake_explanation" in builtin_rule()
with engine.begin() as connection:
    connection.execute(
        insert(skills).values(skill_row(new_id, "错题讲解技能", "mistake_explanation"))
    )
with engine.connect() as connection:
    assert connection.scalar(select(func.count()).select_from(skills)) == 2

with engine.connect() as connection:
    config.attributes["connection"] = connection
    try:
        command.downgrade(config, "0017_teacher_score_override")
    except ValueError as error:
        assert "降级前须删除" in str(error)
    else:
        raise AssertionError("存在错题讲解技能时物理降级必须拒绝")
assert "mistake_explanation" in builtin_rule()

with engine.begin() as connection:
    connection.execute(delete(skills).where(skills.c.id == new_id))
with engine.connect() as connection:
    config.attributes["connection"] = connection
    command.downgrade(config, "0017_teacher_score_override")
    connection.commit()
assert "mistake_explanation" not in builtin_rule()

try:
    with engine.begin() as connection:
        connection.execute(
            insert(skills).values(
                skill_row(str(uuid4()), "不应写入", "mistake_explanation")
            )
        )
except OperationalError as error:
    assert error.orig.args[0] == 3819
else:
    raise AssertionError("旧约束必须拒绝错题讲解技能")

migrate(engine)
with engine.connect() as connection:
    assert (
        connection.scalar(select(skills.c.builtin_key).where(skills.c.id == old_id))
        == "problem_guidance"
    )
print("mistake_explanation_migration_ok")
