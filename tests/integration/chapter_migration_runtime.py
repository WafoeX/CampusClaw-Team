import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import insert, inspect, select, update
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from app.adapters.auth_repository import AuthRepository
from app.adapters.auth_schema_v1 import accounts
from app.adapters.chapter_schema_v4 import chapters
from app.adapters.chapter_schema_v4 import materials as current_materials
from app.adapters.database import mysql_engine
from app.adapters.material_schema_v2 import bodies
from app.adapters.material_schema_v2 import materials as old_materials
from app.adapters.migrations.runner import migrate

engine = mysql_engine(
    host=os.environ["MYSQL_HOST"],
    port=int(os.environ["MYSQL_PORT"]),
    database=os.environ["MYSQL_DATABASE"],
    user=os.environ["MYSQL_USER"],
    password=os.environ["MYSQL_PASSWORD"],
)
assert engine.url.database.startswith("campusclaw_test_")


def down_to_pre_chapters():
    config = Config()
    config.set_main_option(
        "script_location", str(Path("app/adapters/migrations").resolve())
    )
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0003_request_limits")
        connection.commit()


# 上一个集成脚本留下空的 head 库：先回退到 0003，制造真正的旧资料。
down_to_pre_chapters()
assert "chapters" not in inspect(engine).get_table_names()
assert "chapter_id" not in {c["name"] for c in inspect(engine).get_columns("materials")}
AuthRepository(engine).seed_demo_accounts(
    generate_password_hash(os.environ["MYSQL_PASSWORD"], method="scrypt")
)
with engine.connect() as connection:
    actors = {
        row.login_name: row
        for row in connection.execute(
            select(accounts.c.id, accounts.c.class_id, accounts.c.login_name)
        )
    }
teacher_a = actors["demo_a_teacher"]
teacher_b = actors["demo_b_teacher"]
now = datetime.now(UTC).replace(tzinfo=None)
material_a = str(uuid4())
material_b = str(uuid4())
raw = b"\xef\xbb\xbfchapter migration\r\n\x00bytes"
with engine.begin() as connection:
    for identifier, actor in ((material_a, teacher_a), (material_b, teacher_b)):
        connection.execute(
            insert(old_materials).values(
                id=identifier,
                class_id=actor.class_id,
                creator_id=actor.id,
                title="旧资料",
                sort_order=0,
                source_format="txt",
                media_type="text/plain",
                byte_size=len(raw),
                character_count=len(raw),
                content_version=1,
                revision=1,
                created_at=now,
                updated_at=now,
            )
        )
        connection.execute(insert(bodies).values(material_id=identifier, content=raw))

migrate(engine)
migrate(engine)
assert "chapters" in inspect(engine).get_table_names()
with engine.connect() as connection:
    assert (
        connection.scalar(
            select(current_materials.c.chapter_id).where(
                current_materials.c.id == material_a
            )
        )
        is None
    )
    assert (
        connection.scalar(
            select(bodies.c.content).where(bodies.c.material_id == material_a)
        )
        == raw
    )

chapter_a = str(uuid4())
with engine.begin() as connection:
    connection.execute(
        insert(chapters).values(
            id=chapter_a,
            class_id=teacher_a.class_id,
            creator_id=teacher_a.id,
            name="第一章",
            sort_order=0,
            revision=1,
            created_at=now,
            updated_at=now,
        )
    )
    connection.execute(
        update(current_materials)
        .where(current_materials.c.id == material_a)
        .values(chapter_id=chapter_a)
    )
try:
    with engine.begin() as connection:
        connection.execute(
            update(current_materials)
            .where(current_materials.c.id == material_b)
            .values(chapter_id=chapter_a)
        )
except IntegrityError:
    pass
else:
    raise AssertionError("跨班章节外键未拒绝")
with engine.connect() as connection:
    assert (
        connection.scalar(
            select(current_materials.c.chapter_id).where(
                current_materials.c.id == material_b
            )
        )
        is None
    )

# 明确回到章节前的 0003（含其后追加结构），保留原文；重升后恢复未分类。
down_to_pre_chapters()
assert "chapters" not in inspect(engine).get_table_names()
assert "chapter_id" not in {c["name"] for c in inspect(engine).get_columns("materials")}
with engine.connect() as connection:
    assert (
        connection.scalar(
            select(bodies.c.content).where(bodies.c.material_id == material_a)
        )
        == raw
    )
migrate(engine)
with engine.connect() as connection:
    assert (
        connection.scalar(
            select(current_materials.c.chapter_id).where(
                current_materials.c.id == material_a
            )
        )
        is None
    )
    assert (
        connection.scalar(
            select(bodies.c.content).where(bodies.c.material_id == material_a)
        )
        == raw
    )
engine.dispose()
