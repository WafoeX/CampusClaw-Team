"""第 1 组：AP-B01/ST-F06/FB-B01/FB-F04 的存储前置，非完整业务验收。"""

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import event, insert, inspect, select, update
from sqlalchemy.exc import IntegrityError, OperationalError

from app import create_app
from app.adapters.assistant_schema_v8 import (
    TABLES,
    assistant_materials,
    assistant_revisions,
    assistant_skills,
    assistants,
    citations,
    feedback,
    messages,
    operations,
    runs,
    sessions,
    skill_revisions,
    skills,
    template_revisions,
    templates,
)
from app.adapters.auth_schema_v1 import accounts
from app.adapters.chapter_repository import ChapterRepository
from app.adapters.chapter_schema_v4 import chapters
from app.adapters.database import mysql_engine
from app.adapters.material_repository import MaterialRepository
from app.adapters.material_schema_v2 import bodies, deletions, materials
from app.adapters.migrations.runner import migrate
from app.config import Settings

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
now = datetime.now(UTC).replace(tzinfo=None)
expires = now + timedelta(days=30)


def downgrade():
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0007_index_cleanup")


def rows(table):
    with engine.connect() as connection:
        return (
            connection.execute(select(table).order_by(*table.primary_key.columns))
            .mappings()
            .all()
        )


def rejected(table, values, error_code):
    try:
        with engine.begin() as connection:
            connection.execute(insert(table).values(values))
    except (IntegrityError, OperationalError) as error:
        assert error.orig.args[0] == error_code, (table.name, error.orig.args[0])
    else:
        raise AssertionError(f"存储约束未拒绝：{table.name}")


# 既有源码使用的旧字段/原文字节在扩展迁移与回退后必须保持不变。
upstream_accounts = rows(accounts)
upstream_materials = rows(materials)
upstream_bodies = rows(bodies)
downgrade()
assert not ({table.name for table in TABLES} & set(inspect(engine).get_table_names()))


def interrupt_ddl(_connection, _cursor, statement, _parameters, _context, _many):
    if statement.lstrip().startswith("CREATE TABLE sessions"):
        raise RuntimeError("synthetic DDL interruption")


event.listen(engine, "before_cursor_execute", interrupt_ddl)
try:
    try:
        migrate(engine)
    except RuntimeError:
        pass
    else:
        raise AssertionError("DDL 中断未执行")
finally:
    event.remove(engine, "before_cursor_execute", interrupt_ddl)
assert "assistant_materials" in inspect(engine).get_table_names()
assert "sessions" not in inspect(engine).get_table_names()
migrate(engine)
migrate(engine)
assert {table.name for table in TABLES} <= set(inspect(engine).get_table_names())
assert rows(accounts) == upstream_accounts and rows(materials) == upstream_materials
assert rows(bodies) == upstream_bodies
actors = {row["login_name"]: row for row in rows(accounts)}
a, b = actors["demo_a_teacher"], actors["demo_b_teacher"]
student = actors["demo_a_student"]
a_class, a_owner = a["class_id"], student["id"]
config_ids = {}


def config_row(actor, identifier, name):
    return dict(
        id=identifier,
        class_id=actor["class_id"],
        creator_id=actor["id"],
        name=name,
        revision=1,
        enabled=True,
        created_at=now,
        updated_at=now,
    )


with engine.begin() as connection:
    for actor in (a, b):
        aid, sid, tid = (str(uuid4()) for _ in range(3))
        config_ids[actor["class_id"]] = aid, sid, tid
        connection.execute(
            insert(assistants).values(config_row(actor, aid, "合成助手"))
        )
        connection.execute(
            insert(skills).values(
                config_row(actor, sid, "合成技能") | {"name_key": b"synthetic"}
            )
        )
        connection.execute(
            insert(templates).values(
                config_row(actor, tid, "合成模板") | {"app_key": "polish"}
            )
        )
        for table, key, identifier, extra in (
            (assistant_revisions, "assistant_id", aid, {"prompt": ""}),
            (skill_revisions, "skill_id", sid, {"definition": {"steps": []}}),
            (template_revisions, "template_id", tid, {"prompt": "{{input}}"}),
        ):
            connection.execute(
                insert(table).values(
                    class_id=actor["class_id"],
                    **{key: identifier},
                    revision=1,
                    creator_id=actor["id"],
                    created_at=now,
                    **extra,
                )
            )
aid, sid, tid = config_ids[a_class]
rejected(
    assistants,
    config_row(a, str(uuid4()), "越班创建人") | {"creator_id": b["id"]},
    1452,
)
rejected(
    assistant_revisions,
    dict(
        class_id=a_class,
        assistant_id=config_ids[b["class_id"]][0],
        revision=2,
        creator_id=a["id"],
        prompt="",
        created_at=now,
    ),
    1452,
)
rejected(
    template_revisions,
    dict(
        class_id=a_class,
        template_id=tid,
        revision=1,
        creator_id=a["id"],
        prompt="覆盖",
        created_at=now,
    ),
    1062,
)
rejected(
    skills, config_row(a, str(uuid4()), "重复规范名") | {"name_key": b"synthetic"}, 1062
)
rejected(
    assistant_skills,
    dict(
        class_id=a_class,
        assistant_id=aid,
        revision=1,
        skill_id=config_ids[b["class_id"]][1],
    ),
    1452,
)

session_id = str(uuid4())
session_values = dict(
    id=session_id,
    class_id=a_class,
    owner_id=a_owner,
    assistant_id=aid,
    mode="material_qa",
    created_at=now,
    updated_at=now,
    expires_at=expires,
)
rejected(sessions, session_values | {"id": str(uuid4()), "owner_id": b["id"]}, 1452)
with engine.begin() as connection:
    connection.execute(insert(sessions).values(session_values))


def operation_values(key=b"round-one", **changes):
    return (
        dict(
            id=str(uuid4()),
            class_id=a_class,
            owner_id=a_owner,
            session_id=session_id,
            app_key="material_qa",
            operation_scope=session_id.encode(),
            request_key=key,
            fingerprint=b"x" * 32,
            input_payload={"question": "合成问题"},
            status="running",
            attempt_count=1,
            lease_token=str(uuid4()),
            lease_expires_at=now + timedelta(seconds=35),
            created_at=now,
            updated_at=now,
            expires_at=expires,
        )
        | changes
    )


rejected(operations, operation_values(owner_id=a["id"]), 1452)
rejected(operations, operation_values(attempt_count=4), 3819)
rejected(operations, operation_values(lease_token=None), 3819)
rejected(operations, operation_values(operation_scope=b"polish"), 3819)
barrier = Barrier(2)


def accept_round(_):
    values = operation_values()
    barrier.wait(timeout=10)
    try:
        with engine.begin() as connection:
            connection.execute(insert(operations).values(values))
        return values["id"]
    except IntegrityError as error:
        assert error.orig.args[0] == 1062
        return None


with ThreadPoolExecutor(max_workers=2) as workers:
    accepted = list(workers.map(accept_round, range(2)))
assert sum(value is not None for value in accepted) == 1
operation_id = next(value for value in accepted if value)
rejected(operations, operation_values(b"other-key"), 1062)
user_id, answer_id, run_id = (str(uuid4()) for _ in range(3))
message_base = dict(
    class_id=a_class,
    owner_id=a_owner,
    session_id=session_id,
    operation_id=operation_id,
    content_state="available",
    created_at=now,
    expires_at=expires,
)
run_base = dict(
    class_id=a_class,
    owner_id=a_owner,
    operation_id=operation_id,
    configuration={"template_revision": 1},
    created_at=now,
    updated_at=now,
    expires_at=expires,
)
rejected(
    messages,
    message_base
    | {"id": str(uuid4()), "owner_id": a["id"], "role": "user", "content": "偷换本人"},
    1452,
)
with engine.begin() as connection:
    connection.execute(
        insert(messages).values(
            message_base | {"id": user_id, "role": "user", "content": "合成问题"}
        )
    )
    connection.execute(
        insert(messages).values(
            message_base
            | {"id": answer_id, "role": "assistant", "content": "合成资料回答"}
        )
    )
    connection.execute(
        insert(runs).values(
            run_base
            | {
                "id": run_id,
                "attempt": 1,
                "status": "succeeded",
                "details": {"answer": "合成资料回答"},
            }
        )
    )
    connection.execute(
        update(operations)
        .where(operations.c.id == operation_id)
        .values(status="succeeded", lease_token=None, lease_expires_at=None)
    )
rejected(
    messages,
    message_base | {"id": str(uuid4()), "role": "user", "content": "重复"},
    1062,
)
rejected(
    messages,
    message_base | {"id": str(uuid4()), "role": "assistant", "content": "重复"},
    1062,
)

rejected(
    runs,
    run_base | {"id": str(uuid4()), "attempt": 2, "status": "succeeded", "details": {}},
    1062,
)
rejected(
    runs,
    run_base
    | {
        "id": str(uuid4()),
        "attempt": 2,
        "status": "failed",
        "details": {"unsafe": "未校验"},
    },
    3819,
)
with engine.begin() as connection:
    connection.execute(
        insert(runs).values(
            run_base
            | {
                "id": str(uuid4()),
                "attempt": 2,
                "status": "failed",
                "details": None,
                "error_code": 1500,
            }
        )
    )
    # 成功轮次释放会话在途槽位；幂等键大小写敏感。
    connection.execute(insert(operations).values(operation_values(b"Round-one")))

# 用真实受保护资料入口建立、删除资料，来源副本由 schema 夹具生成。
origin = "https://campusclaw.test"
settings = replace(
    Settings.load(os.environ, Path("app/BUILD_VERSION")), public_origin=origin
)
app = create_app(settings)
client = app.test_client()
headers = {"Origin": origin, "X-CampusClaw-Request": "same-origin"}
assert (
    client.post(
        "/api/v1/auth/sessions",
        base_url=origin,
        headers=headers,
        json={"login_name": a["login_name"], "password": os.environ["MYSQL_PASSWORD"]},
    ).status_code
    == 200
)
created = client.post(
    "/api/v1/materials",
    base_url=origin,
    headers=headers | {"Idempotency-Key": "storage-fixture"},
    json={"title": "存储合成原文", "text": "合成依据😀"},
)
assert created.status_code == 201, created.json
material_id = created.json["data"]["id"]
other_source = client.post(
    "/api/v1/materials",
    base_url=origin,
    headers=headers | {"Idempotency-Key": "storage-other-source"},
    json={"title": "另一来源", "text": "次要依据"},
)
assert other_source.status_code == 201
other_material_id = other_source.json["data"]["id"]
chapter_id = str(uuid4())
with engine.begin() as connection:
    connection.execute(
        insert(chapters).values(
            id=chapter_id,
            class_id=a_class,
            creator_id=a["id"],
            name="存储章节",
            sort_order=0,
            revision=1,
            created_at=now,
            updated_at=now,
        )
    )
    connection.execute(
        insert(assistant_materials).values(
            class_id=a_class, assistant_id=aid, revision=1, material_id=material_id
        )
    )
    citation_values = dict(
        class_id=a_class,
        owner_id=a_owner,
        session_id=session_id,
        message_id=answer_id,
        ordinal=1,
        material_id=material_id,
        source_version=1,
        index_version=1,
        index_config_version="f" * 64,
        start_offset=0,
        end_offset=5,
        title="存储合成原文",
        excerpt="合成依据😀",
        status="available",
        created_at=now,
        expires_at=expires,
    )
    connection.execute(insert(citations).values(citation_values))
    connection.execute(
        insert(citations).values(
            citation_values
            | {
                "ordinal": 2,
                "material_id": other_material_id,
                "end_offset": 4,
                "title": "另一来源",
                "excerpt": "次要依据",
            }
        )
    )
    feedback_values = dict(
        id=str(uuid4()),
        class_id=a_class,
        owner_id=a_owner,
        session_id=session_id,
        message_id=answer_id,
        chapter_id=chapter_id,
        rating="unresolved",
        note="合成卡点",
        status="pending",
        revision=1,
        creator_id=a_owner,
        created_at=now,
        updated_at=now,
        expires_at=expires,
    )
    connection.execute(insert(feedback).values(feedback_values))
rejected(
    citations, citation_values | {"message_id": user_id, "owner_id": a["id"]}, 1452
)
rejected(citations, citation_values | {"ordinal": 3, "end_offset": 6}, 3819)
rejected(
    assistant_materials,
    dict(
        class_id=b["class_id"],
        assistant_id=config_ids[b["class_id"]][0],
        revision=1,
        material_id=material_id,
    ),
    1452,
)
with engine.begin() as connection:
    ChapterRepository(engine).clear_chapter(connection, a_class, chapter_id, now)
assert (
    next(row for row in rows(feedback) if row["message_id"] == answer_id)["chapter_id"]
    is None
)

# 保留隔离行快照，在同一专用库中模拟旧备份行还原，不称作生产备份演练。
copy_tables = [operations, messages, runs, citations, feedback]
saved = {table: rows(table) for table in copy_tables}
saved_material = next(row for row in rows(materials) if row["id"] == material_id)
saved_body = next(row for row in rows(bodies) if row["material_id"] == material_id)


def assert_copies_hidden():
    own_messages = [
        row for row in rows(messages) if row["operation_id"] == operation_id
    ]
    assert len(own_messages) == 2 and all(
        row["content"] is None and row["content_state"] == "revoked"
        for row in own_messages
    )
    assert all(
        row["details"] is None
        for row in rows(runs)
        if row["operation_id"] == operation_id
    )
    source = next(row for row in rows(citations) if row["message_id"] == answer_id)
    assert (
        source["status"] == "deleted"
        and source["title"] is None
        and source["excerpt"] is None
    )
    assert (
        next(row for row in rows(operations) if row["id"] == operation_id)[
            "input_payload"
        ]
        is None
    )
    note = next(row for row in rows(feedback) if row["message_id"] == answer_id)
    assert note["status"] == "unavailable" and note["note"] is None


def interrupt_cleanup(_connection, _cursor, statement, _parameters, _context, _many):
    if statement.startswith("UPDATE message_citations"):
        raise OperationalError(
            statement, None, Exception("synthetic copy cleanup failure")
        )


# FB-F04：失败后原文和所有副本同事务回滚，不出现半删。
event.listen(engine, "before_cursor_execute", interrupt_cleanup)
try:
    try:
        with engine.begin() as connection:
            MaterialRepository(engine).remove(connection, material_id, now)
    except OperationalError:
        pass
    else:
        raise AssertionError("副本故障未注入")
finally:
    event.remove(engine, "before_cursor_execute", interrupt_cleanup)
assert all(rows(table) == saved[table] for table in copy_tables)
assert saved_body in rows(bodies)
response = client.delete(
    f"/api/v1/materials/{material_id}", base_url=origin, headers=headers
)
assert response.status_code == 200, response.json
assert_copies_hidden()
rejected(
    runs,
    run_base | {"id": str(uuid4()), "attempt": 3, "status": "succeeded", "details": {}},
    1062,
)
assert not any(row["material_id"] == material_id for row in rows(assistant_materials))

# 多来源依次删除，不得将已删除来源退回 revoked，反复重放不抬高反馈修订。
assert (
    client.delete(
        f"/api/v1/materials/{other_material_id}", base_url=origin, headers=headers
    ).status_code
    == 200
)
assert all(
    row["status"] == "deleted"
    for row in rows(citations)
    if row["message_id"] == answer_id
)
redacted_revision = next(
    row for row in rows(feedback) if row["message_id"] == answer_id
)["revision"]
# 恢复旧行后重放独立删除凭证两次，仍清除全部衍生正文。
manifest = [
    (row["material_id"], row["deleted_at"])
    for row in rows(deletions)
    if row["material_id"] in (material_id, other_material_id)
]
with engine.begin() as connection:
    connection.execute(insert(materials).values(saved_material))
    connection.execute(insert(bodies).values(saved_body))
    for table in copy_tables:
        primary = [column.name for column in table.primary_key.columns]
        for saved_row in saved[table]:
            writable = {
                key: value
                for key, value in saved_row.items()
                if not table.c[key].computed and key not in primary
            }
            condition = [table.c[key] == saved_row[key] for key in primary]
            connection.execute(update(table).where(*condition).values(writable))
MaterialRepository(engine).replay_deletions(manifest)
MaterialRepository(engine).replay_deletions(manifest)
assert_copies_hidden()
assert all(
    row["status"] == "deleted"
    for row in rows(citations)
    if row["message_id"] == answer_id
)
assert (
    next(row for row in rows(feedback) if row["message_id"] == answer_id)["revision"]
    == redacted_revision
)
assert not any(row["material_id"] == material_id for row in rows(bodies))
# 单步物理回退仅在合成库，旧数据不丢；重升为空扩展表。
downgrade()
assert rows(accounts) == upstream_accounts
assert rows(materials) == upstream_materials and rows(bodies) == upstream_bodies
migrate(engine)
assert all(not rows(table) for table in TABLES)
engine.dispose()
print(
    "第1组存储：中断迁移/重跑/回退、同班本人约束、并发唯一成功、删除回滚及恢复重放通过"
)
