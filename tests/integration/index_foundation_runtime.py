"""Task 2.1：真实 MySQL 索引结构、全文与兼容迁移。"""

import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import event, insert, inspect, select, text
from sqlalchemy.exc import IntegrityError, OperationalError

from app.adapters.auth_schema_v1 import accounts
from app.adapters.chapter_schema_v4 import chapters
from app.adapters.chapter_schema_v4 import materials as old_materials
from app.adapters.database import mysql_engine
from app.adapters.index_schema_v5 import builds, chunks, cleanups, materials
from app.adapters.material_schema_v2 import bodies
from app.adapters.migrations.runner import migrate
from app.services.chunking import ChunkConfig, split_source
from app.services.index_scope import IndexScope

engine = mysql_engine(
    host=os.environ["MYSQL_HOST"],
    port=int(os.environ["MYSQL_PORT"]),
    database=os.environ["MYSQL_DATABASE"],
    user=os.environ["MYSQL_USER"],
    password=os.environ["MYSQL_PASSWORD"],
)
assert engine.url.database.startswith("campusclaw_test_")
config = Config()
config.set_main_option("script_location", str(Path("app/adapters/migrations")))


def down_to_chapters():
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0004_chapters")


with engine.connect() as connection:
    original_materials = connection.execute(
        select(old_materials).order_by(old_materials.c.id)
    ).all()
    original_bodies = connection.execute(
        select(bodies).order_by(bodies.c.material_id)
    ).all()
    original_chapters = connection.execute(
        select(chapters).order_by(chapters.c.id)
    ).all()

down_to_chapters()
assert "material_chunks" not in inspect(engine).get_table_names()
# 模拟 MySQL DDL 已提交但版本尚未前进的中断，重跑须从已有列继续。
with engine.begin() as connection:
    connection.execute(
        text("ALTER TABLE materials ADD COLUMN active_index_version INTEGER NULL")
    )
migrate(engine)
migrate(engine)
with engine.connect() as connection:
    assert (
        connection.execute(select(old_materials).order_by(old_materials.c.id)).all()
        == original_materials
    )
    assert (
        connection.execute(select(bodies).order_by(bodies.c.material_id)).all()
        == original_bodies
    )
    assert (
        connection.execute(select(chapters).order_by(chapters.c.id)).all()
        == original_chapters
    )
    assert all(
        row == (None, None, False)
        for row in connection.execute(
            select(
                materials.c.active_index_version,
                materials.c.desired_index_version,
                materials.c.vector_ready,
            )
        )
    )
    assert connection.execute(
        text("SELECT @@ngram_token_size, @@innodb_ft_enable_stopword")
    ).one() == (2, 0)
    ddl = connection.execute(text("SHOW CREATE TABLE material_chunks")).one()[1]
    assert "FULLTEXT KEY `ft_chunks_content`" in ddl and "ngram" in ddl
    assert "utf8mb4_0900_ai_ci" in ddl
    teachers = {
        row.login_name: row
        for row in connection.execute(
            select(accounts).where(
                accounts.c.login_name.in_(["demo_a_teacher", "demo_b_teacher"])
            )
        )
    }

now = datetime.now(UTC).replace(tzinfo=None)
configuration = ChunkConfig()
fixtures = []
for login_name, source in [
    ("demo_a_teacher", "数据库事务与数据库隔离，数据库事务保证原子性。" * 12),
    ("demo_a_teacher", "数据库课程介绍，先阅读资料。"),
    ("demo_b_teacher", "仅乙班秘密：数据库事务与数据库隔离。"),
]:
    actor = teachers[login_name]
    material_id = str(uuid4())
    raw = b"\xef\xbb\xbf" + ("# 资料😀\r\n" + source + "\r\n").encode()
    scope = IndexScope(actor.class_id, material_id, 1, 1, configuration.version)
    pieces = split_source(raw, "md", material_id, 1)
    with engine.begin() as connection:
        connection.execute(
            insert(old_materials).values(
                id=material_id,
                class_id=actor.class_id,
                creator_id=actor.id,
                chapter_id=None,
                title="索引测试资料",
                sort_order=0,
                source_format="md",
                media_type="text/markdown",
                byte_size=len(raw),
                character_count=len(raw.decode("utf-8-sig")),
                content_version=1,
                revision=1,
                created_at=now,
                updated_at=now,
            )
        )
        connection.execute(insert(bodies).values(material_id=material_id, content=raw))
        connection.execute(
            insert(builds).values(
                id=str(uuid4()),
                **scope.fields,
                creator_id=actor.id,
                mode="auto",
                window_size=600,
                overlap=80,
                status="building",
                stage="chunks",
                lease_expires_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        connection.execute(
            insert(chunks),
            [
                dict(
                    id=piece.id,
                    **scope.fields,
                    ordinal=piece.ordinal,
                    start_offset=piece.start,
                    end_offset=piece.end,
                    content=piece.text,
                )
                for piece in pieces
            ],
        )
    fixtures.append((scope, raw, pieces))

query = text("""
    SELECT id, material_id, content,
           MATCH(content) AGAINST (:query IN NATURAL LANGUAGE MODE) AS score
      FROM material_chunks
     WHERE class_id = :class_id
       AND MATCH(content) AGAINST (:query IN NATURAL LANGUAGE MODE) > 0
     ORDER BY score DESC, id LIMIT 20
""")
with engine.connect() as connection:
    arguments = {"query": "数据库事务", "class_id": teachers["demo_a_teacher"].class_id}
    hits = connection.execute(query, arguments).mappings().all()
    assert hits and hits[0]["material_id"] == fixtures[0][0].material_id
    assert all(hit["score"] > 0 and "仅乙班" not in hit["content"] for hit in hits)
    assert connection.execute(query, arguments).mappings().all() == hits
    assert not connection.execute(query, {**arguments, "query": "火星探测"}).all()
    assert not connection.execute(query, {**arguments, "query": "数"}).all()
    for scope, raw, pieces in fixtures:
        stored = (
            connection.execute(
                select(chunks).where(chunks.c.material_id == scope.material_id)
            )
            .mappings()
            .all()
        )
        assert [row["content"] for row in stored] == [piece.text for piece in pieces]
        assert (
            connection.scalar(
                select(bodies.c.content).where(
                    bodies.c.material_id == scope.material_id
                )
            )
            == raw
        )
        assert set(scope.payload(pieces[0].id)) == {
            "class_id",
            "material_id",
            "source_version",
            "index_version",
            "index_config_version",
            "scope_key",
            "chunk_id",
        }

# 同班外键、构建配置/原文版本和坐标由真实数据库约束保护。
sample = dict(
    id=str(uuid4()),
    **fixtures[0][0].fields,
    ordinal=1,
    start_offset=0,
    end_offset=2,
    content="测试",
)
for changes in (
    {"class_id": teachers["demo_b_teacher"].class_id},
    {"source_version": 2},
    {"index_config_version": "0" * 64},
    {"end_offset": 3},
):
    try:
        with engine.begin() as connection:
            connection.execute(insert(chunks).values(sample | changes))
    except (IntegrityError, OperationalError) as error:
        assert error.orig.args[0] == (3819 if "end_offset" in changes else 1452)
    else:
        raise AssertionError("索引归属、版本或坐标约束未生效")


# 写入故障应回滚完整切片批次。
insert_attempts = 0


def interrupt_insert(_connection, _cursor, statement, _parameters, _context, _many):
    global insert_attempts
    if statement.startswith("INSERT INTO material_chunks"):
        insert_attempts += 1
        if insert_attempts == 2:
            raise RuntimeError("synthetic chunk interruption")


with engine.connect() as connection:
    count_before = len(connection.execute(select(chunks.c.id)).all())
event.listen(engine, "before_cursor_execute", interrupt_insert)
try:
    try:
        with engine.begin() as connection:
            connection.execute(insert(chunks).values(sample))
            connection.execute(
                insert(chunks).values(sample | {"id": str(uuid4()), "ordinal": 2})
            )
    except RuntimeError:
        pass
    else:
        raise AssertionError("故障未注入")
finally:
    event.remove(engine, "before_cursor_execute", interrupt_insert)
with engine.connect() as connection:
    assert insert_attempts == 2
    assert len(connection.execute(select(chunks.c.id)).all()) == count_before

# 去内容清理记录不依赖仍存在的资料，覆盖后续删除补偿契约。
deleted_scope = IndexScope(
    teachers["demo_a_teacher"].class_id, str(uuid4()), 1, 1, configuration.version
)
with engine.begin() as connection:
    connection.execute(
        insert(cleanups).values(
            id=str(uuid4()),
            **deleted_scope.fields,
            scope_key=deleted_scope.key,
            status="pending",
            attempts=0,
            created_at=now,
            updated_at=now,
        )
    )

down_to_chapters()
with engine.connect() as connection:
    for scope, raw, _ in fixtures:
        assert (
            connection.scalar(
                select(bodies.c.content).where(
                    bodies.c.material_id == scope.material_id
                )
            )
            == raw
        )
assert "material_index_builds" not in inspect(engine).get_table_names()
migrate(engine)
with engine.connect() as connection:
    assert not connection.execute(select(chunks.c.id)).all()
    assert (
        connection.execute(select(chapters).order_by(chapters.c.id)).all()
        == original_chapters
    )
    assert (
        connection.execute(
            select(bodies)
            .where(
                bodies.c.material_id.in_([row.material_id for row in original_bodies])
            )
            .order_by(bodies.c.material_id)
        ).all()
        == original_bodies
    )
engine.dispose()
print("Task 2.1：旧库/中断恢复/重跑/回退、原文保真、中文全文与版本外键通过")
