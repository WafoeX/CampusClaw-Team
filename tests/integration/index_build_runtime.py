"""Task 2.2：真实 MySQL/Qdrant，嵌入使用明确的确定性替身。"""

import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from threading import Event
from uuid import uuid4

from sqlalchemy import event, insert, select, update
from sqlalchemy.exc import OperationalError
from werkzeug.security import generate_password_hash

from app import create_app
from app.adapters.auth_repository import AuthRepository
from app.adapters.auth_schema_v1 import accounts, classes
from app.adapters.database import DatabaseError, mysql_engine
from app.adapters.index_cleanup_repository import IndexCleanupRepository
from app.adapters.index_clients import IndexDependencyError, QdrantIndexClient
from app.adapters.index_receipts import record_cleanup
from app.adapters.index_repository import IndexRepository
from app.adapters.index_schema_v5 import chunks, materials
from app.adapters.index_schema_v7 import builds, cleanups, tombstones
from app.adapters.material_repository import MaterialRepository
from app.adapters.material_schema_v2 import bodies
from app.api.auth import COOKIE
from app.config import EmbeddingSettings, Settings
from app.services.access import Identity
from app.services.auth import utc_now
from app.services.chunking import Chunk, ChunkConfig
from app.services.index_cleanup import IndexCleanupService
from app.services.index_scope import IndexScope
from app.services.indexing import IndexService
from app.services.materials import MaterialService

engine = mysql_engine(
    host=os.environ["MYSQL_HOST"],
    port=int(os.environ["MYSQL_PORT"]),
    database=os.environ["MYSQL_DATABASE"],
    user=os.environ["MYSQL_USER"],
    password=os.environ["MYSQL_PASSWORD"],
)
assert engine.url.database.startswith("campusclaw_test_")
origin = "https://campusclaw.test"
config = EmbeddingSettings(
    "https://ai-gateway.devops.hello1023.com/v1", "", "course-embedding", 2048
)
settings = replace(
    Settings.load(os.environ, Path("app/BUILD_VERSION")),
    public_origin=origin,
    embedding=config,
)
headers = {"Origin": origin, "X-CampusClaw-Request": "same-origin"}
# 各专项使用自己的账号与班级，避免复用章节夹具耗尽同一真实账号配额。
with engine.begin() as connection:
    class_ids = {section: str(uuid4()) for section in ("a", "b")}
    now = utc_now()
    for section, class_id in class_ids.items():
        connection.execute(
            insert(classes).values(
                id=class_id,
                code="ix-" + section,
                name="索引合成班" + section,
                created_at=now,
            )
        )
    for name, section, role in [
        ("ix_a_teacher", "a", "teacher"),
        ("ix_a_student", "a", "student"),
        ("ix_b_teacher", "b", "teacher"),
    ]:
        connection.execute(
            insert(accounts).values(
                id=str(uuid4()),
                login_name=name,
                class_id=class_ids[section],
                role=role,
                enabled=True,
                password_hash=generate_password_hash(
                    os.environ["MYSQL_PASSWORD"], method="scrypt"
                ),
                created_at=now,
                updated_at=now,
            )
        )


class SyntheticEmbedding:
    calls = 0
    fail = False

    def embed(self, texts, deadline, *, before_call=None):
        self.calls += 1
        if before_call:
            before_call()
        if self.fail:
            raise IndexDependencyError("synthetic_failure")
        return [[1.0] + [0.0] * 2047 for _ in texts]


embedding = SyntheticEmbedding()
vectors = QdrantIndexClient(settings.qdrant_url, settings.qdrant_api_key, config)
service = IndexService(
    IndexRepository(engine),
    DatabaseError,
    embedding,
    vectors,
    IndexDependencyError,
    config.version,
)
app = create_app(
    settings,
    indexing=service,
    materials=MaterialService(MaterialRepository(engine), DatabaseError),
)


def login(name):
    client = app.test_client()
    result = client.post(
        "/api/v1/auth/sessions",
        base_url=origin,
        headers=headers,
        json={"login_name": name, "password": os.environ["MYSQL_PASSWORD"]},
    )
    assert result.status_code == 200
    return client


teacher, student, outsider = [
    login(name) for name in ("ix_a_teacher", "ix_a_student", "ix_b_teacher")
]
created = teacher.post(
    "/api/v1/materials",
    base_url=origin,
    headers={**headers, "Idempotency-Key": str(uuid4())},
    json={"title": "构建夹具", "text": "中文资料甲乙丙丁\r\n" * 200},
)
assert created.status_code == 201
material_id = created.json["data"]["id"]
path = "/api/v1/materials/" + material_id + "/index-builds"


def build(key, client=teacher, **fields):
    return client.post(
        path, base_url=origin, headers={**headers, "Idempotency-Key": key}, json=fields
    )


# IX-F02/F03：授权与同构，外部调用为零。
for actor, status in ((student, 403), (app.test_client(), 401), (outsider, 404)):
    rejected = build("reject", actor)
    assert rejected.status_code == status and rejected.json["data"] is None
assert embedding.calls == 0
assert teacher.get(path, base_url=origin).json["data"]["items"] == []

# IX-N01：完整写入、真实回读核验以及幂等重放。
result = build("first")
assert result.status_code == 201 and result.json["code"] == 0
first = result.json["data"]
assert first["status"] == "published"
assert teacher.get(path + "/" + first["id"], base_url=origin).json["data"] == first
assert build("first").status_code == 200 and embedding.calls == 1
assert build("first", mode="custom", window=100, overlap=0).status_code == 409
with engine.connect() as connection:
    row = (
        connection.execute(select(materials).where(materials.c.id == material_id))
        .mappings()
        .one()
    )
    assert row["active_index_version"] == 1 and row["vector_ready"]
    persisted = (
        connection.execute(select(chunks).where(chunks.c.material_id == material_id))
        .mappings()
        .all()
    )
    assert persisted and all(
        part["content"]
        == ("中文资料甲乙丙丁\r\n" * 200)[part["start_offset"] : part["end_offset"]]
        for part in persisted
    )

# IX-F04：失败重建保留完整旧版，故障解除后显式新键发布。
embedding.fail = True
failed = build("second")
assert failed.status_code == 503
with engine.connect() as connection:
    assert (
        connection.scalar(
            select(materials.c.active_index_version).where(
                materials.c.id == material_id
            )
        )
        == 1
    )
    state = (
        connection.execute(
            select(builds).where(
                builds.c.material_id == material_id, builds.c.index_version == 2
            )
        )
        .mappings()
        .one()
    )
    assert state["status"] == "failed"
embedding.fail = False
assert build("third").status_code == 201
with engine.connect() as connection:
    assert (
        connection.scalar(
            select(materials.c.active_index_version).where(
                materials.c.id == material_id
            )
        )
        == 3
    )

# 首次构建缺嵌入依赖时保留关键词，而非删除原文。
new = teacher.post(
    "/api/v1/materials",
    base_url=origin,
    headers={**headers, "Idempotency-Key": str(uuid4())},
    json={"title": "首次故障", "text": "首次关键词可用"},
)
new_id = new.json["data"]["id"]
embedding.fail = True
failure = teacher.post(
    "/api/v1/materials/" + new_id + "/index-builds",
    base_url=origin,
    headers={**headers, "Idempotency-Key": "initial-failure"},
    json={},
)
assert failure.status_code == 503
with engine.connect() as connection:
    target = (
        connection.execute(select(materials).where(materials.c.id == new_id))
        .mappings()
        .one()
    )
    assert target["active_index_version"] == 1 and not target["vector_ready"]
    assert (
        connection.scalar(select(builds.c.status).where(builds.c.material_id == new_id))
        == "keyword_only"
    )
assert (
    teacher.get("/api/v1/materials/" + new_id + "/download", base_url=origin).data
    == "首次关键词可用".encode()
)
embedding.fail = False

# IX-F05：多请求共享班级租约；过期执行者不得迟到发布。

entered, release = Event(), Event()
original_embed = embedding.embed


def paused_embed(texts, deadline, *, before_call=None):
    entered.set()
    assert release.wait(8)
    return original_embed(texts, deadline, before_call=before_call)


embedding.embed = paused_embed
with ThreadPoolExecutor(max_workers=1) as pool:
    pending = pool.submit(build, "paused")
    assert entered.wait(8)
    replay = build("paused")
    assert replay.status_code == 200 and replay.json["data"]["status"] == "building"
    assert build("different-key").status_code == 409
    other = teacher.post(
        "/api/v1/materials/" + new_id + "/index-builds",
        base_url=origin,
        headers={**headers, "Idempotency-Key": "class-conflict"},
        json={},
    )
    assert other.status_code == 429
    with engine.begin() as connection:
        current = (
            connection.execute(
                select(builds).where(builds.c.id == replay.json["data"]["id"])
            )
            .mappings()
            .one()
        )
        connection.execute(
            update(builds)
            .where(builds.c.id == current["id"])
            .values(lease_expires_at=service.clock() - timedelta(seconds=1))
        )
    release.set()
    late = pending.result(timeout=10)
    assert late.status_code == 409
embedding.embed = original_embed
with engine.connect() as connection:
    assert (
        connection.scalar(
            select(materials.c.active_index_version).where(
                materials.c.id == material_id
            )
        )
        == 3
    )
assert build("after-expiry").status_code == 201

# IX-F02：调用在途撤销教师权限，发布前必须重新校验。
entered.clear()
release.clear()
embedding.embed = paused_embed
with ThreadPoolExecutor(max_workers=1) as pool:
    pending = pool.submit(build, "revoked-in-flight")
    assert entered.wait(8)
    with engine.begin() as connection:
        connection.execute(
            update(accounts)
            .where(accounts.c.login_name == "ix_a_teacher")
            .values(role="student")
        )
    release.set()
    revoked = pending.result(timeout=10)
    assert revoked.status_code == 403
embedding.embed = original_embed
with engine.begin() as connection:
    connection.execute(
        update(accounts)
        .where(accounts.c.login_name == "ix_a_teacher")
        .values(role="teacher")
    )

# IX-F04：真实向量部分写和 payload 错配均不得发布，并精确清理。
with engine.connect() as connection:
    before_version = connection.scalar(
        select(materials.c.active_index_version).where(materials.c.id == material_id)
    )
original_write, original_verify = vectors.write, vectors.verify


def partial_write(scope, parts, values, deadline):
    original_write(scope, parts[:1], values[:1], deadline)
    raise IndexDependencyError("synthetic_partial_write")


vectors.write = partial_write
assert build("partial-write").status_code == 503
vectors.write = original_write


def mismatch(scope, parts, deadline):
    vectors.endpoint.request(
        "POST",
        vectors.path + "/points/payload?wait=true",
        {"points": [parts[0].id], "payload": {"chunk_id": "wrong-identity"}},
        deadline,
    )
    original_verify(scope, parts, deadline)


vectors.verify = mismatch
assert build("point-mismatch").status_code == 503
vectors.verify = original_verify
with engine.connect() as connection:
    assert (
        connection.scalar(
            select(materials.c.active_index_version).where(
                materials.c.id == material_id
            )
        )
        == before_version
    )
assert build("after-vector-faults").status_code == 201

# 进程退出后的显式恢复有界且可重跑。

account = AuthRepository(engine).find_account("ix_a_teacher")
identity = Identity(account.id, account.class_id, frozenset({"materials:write"}))
cookie = teacher.get_cookie(COOKIE, domain="campusclaw.test").value
orphan, _ = service.prepare(identity, cookie, material_id, b"orphan", ChunkConfig())
with engine.begin() as connection:
    connection.execute(
        update(builds)
        .where(builds.c.id == orphan["id"])
        .values(lease_expires_at=service.clock() - timedelta(seconds=1))
    )
assert service.recover() == 1
assert service.recover() == 0
assert (
    teacher.get(path + "/" + orphan["id"], base_url=origin).json["data"]["stage"]
    == "lease_expired"
)
assert build("after-recovery").status_code == 201

# IX-B01：恰好64片，首次关键词与完整旧版重建的可见性。
boundary_source = "边" * 6400
boundary = teacher.post(
    "/api/v1/materials",
    base_url=origin,
    headers={**headers, "Idempotency-Key": "sixty-four-source"},
    json={"title": "64片边界", "text": boundary_source},
).json["data"]["id"]
boundary_path = "/api/v1/materials/" + boundary + "/index-builds"
verify_original = vectors.verify
for expected_version in (1, 2):
    entered.clear()
    release.clear()

    def pause_verify(scope, parts, deadline):
        assert len(parts) == 64
        entered.set()
        assert release.wait(8)
        verify_original(scope, parts, deadline)

    vectors.verify = pause_verify
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(
            teacher.post,
            boundary_path,
            base_url=origin,
            headers={
                **headers,
                "Idempotency-Key": "sixty-four-" + str(expected_version),
            },
            json={"mode": "custom", "window": 100, "overlap": 0},
        )
        assert entered.wait(8)
        states = teacher.get(boundary_path, base_url=origin).json["data"]["items"]
        assert (
            states[0]["status"] == "building" and states[0]["stage"] == "vector_verify"
        )
        with engine.connect() as connection:
            active_boundary = (
                connection.execute(select(materials).where(materials.c.id == boundary))
                .mappings()
                .one()
            )
            assert active_boundary["active_index_version"] == 1
            assert active_boundary["vector_ready"] == (expected_version == 2)
        student_download = teacher.get(
            "/api/v1/materials/" + boundary + "/download", base_url=origin
        )
        assert student_download.data == boundary_source.encode()
        release.set()
        assert pending.result(timeout=10).status_code == 201
vectors.verify = verify_original

# IX-B02：真实入口的32000/32001码点，超限无构建及外部副作用。
capacity_source = ("甲" * 300 + "\n\n") * 105
capacity_source += "乙" * (32000 - len(capacity_source))
for extra in ("", "丙"):
    source = capacity_source + extra
    created_capacity = teacher.post(
        "/api/v1/materials",
        base_url=origin,
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"title": "容量边界", "text": source},
    )
    assert created_capacity.status_code == 201
    capacity_id = created_capacity.json["data"]["id"]
    capacity_path = "/api/v1/materials/" + capacity_id + "/index-builds"
    before_calls = embedding.calls
    capacity_result = teacher.post(
        capacity_path,
        base_url=origin,
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={},
    )
    if extra:
        assert capacity_result.status_code == 400 and embedding.calls == before_calls
        assert teacher.get(capacity_path, base_url=origin).json["data"]["items"] == []
    else:
        assert capacity_result.status_code == 201
        with engine.connect() as connection:
            capacity_chunks = (
                connection.execute(
                    select(chunks).where(chunks.c.material_id == capacity_id)
                )
                .mappings()
                .all()
            )
        assert (
            len(capacity_chunks) == 62
            and max(row["end_offset"] for row in capacity_chunks) == 32000
        )
    assert (
        teacher.get(
            "/api/v1/materials/" + capacity_id + "/download", base_url=origin
        ).data
        == source.encode()
    )

# Task 2.3：旧切片转为无正文映射，删除事务回退、迟到向量和恢复清单。
with engine.connect() as connection:
    saved_material = dict(
        connection.execute(select(materials).where(materials.c.id == material_id))
        .mappings()
        .one()
    )
    saved_body = dict(
        connection.execute(select(bodies).where(bodies.c.material_id == material_id))
        .mappings()
        .one()
    )
    saved_builds = [
        dict(row)
        for row in connection.execute(
            select(builds).where(builds.c.material_id == material_id)
        ).mappings()
    ]
    saved_chunks = [
        dict(row)
        for row in connection.execute(
            select(chunks).where(chunks.c.material_id == material_id)
        ).mappings()
    ]
    old_mappings = (
        connection.execute(
            select(tombstones).where(tombstones.c.material_id == material_id)
        )
        .mappings()
        .all()
    )
    assert old_mappings and all("content" not in row for row in old_mappings)
    assert all(
        row["index_version"] == saved_material["active_index_version"]
        for row in saved_chunks
    )
    cleanup_before = connection.execute(select(cleanups)).all()


def interrupt_delete(_conn, _cursor, statement, _parameters, _context, _many):
    if statement.startswith("DELETE FROM materials"):
        raise OperationalError(None, None, RuntimeError("synthetic rollback"))


event.listen(engine, "before_cursor_execute", interrupt_delete)
try:
    refused = teacher.delete(
        "/api/v1/materials/" + material_id, base_url=origin, headers=headers
    )
    assert refused.status_code == 503, (refused.status_code, refused.json)
finally:
    event.remove(engine, "before_cursor_execute", interrupt_delete)
with engine.connect() as connection:
    assert connection.execute(select(cleanups)).all() == cleanup_before
    assert len(
        connection.execute(
            select(chunks).where(chunks.c.material_id == material_id)
        ).all()
    ) == len(saved_chunks)
assert (
    teacher.get("/api/v1/materials/" + material_id + "/download", base_url=origin).data
    == saved_body["content"]
)

# 删除索引资料必须继续原子撤权，并持久化无正文清理凭证。
# 在写向量前暂停已受理重建；删除先提交，迟到写即使成功也不能发布。
entered.clear()
release.clear()
original_delete = vectors.delete
write_before_delete = vectors.write


def late_write(scope, parts, values, deadline):
    entered.set()
    assert release.wait(8)
    write_before_delete(scope, parts, values, deadline)


def unavailable_delete(scope, deadline):
    raise IndexDependencyError("synthetic_delete_unavailable")


vectors.write = late_write
vectors.delete = unavailable_delete
with ThreadPoolExecutor(max_workers=1) as pool:
    pending = pool.submit(build, "delete-in-flight")
    reached = entered.wait(8)
    if not reached and pending.done():
        early = pending.result()
        raise AssertionError(("构建未到达向量写入", early.status_code, early.json))
    assert reached
    deleted = teacher.delete(
        "/api/v1/materials/" + material_id, base_url=origin, headers=headers
    )
    assert deleted.status_code == 200
    release.set()
    late = pending.result(timeout=10)
    assert late.status_code == 404 and late.json["data"] is None
vectors.write = write_before_delete
vectors.delete = original_delete
assert (
    teacher.delete(
        "/api/v1/materials/" + material_id, base_url=origin, headers=headers
    ).status_code
    == 404
)
assert teacher.get(path, base_url=origin).status_code == 404
with engine.connect() as connection:
    assert not connection.execute(
        select(chunks.c.id).where(chunks.c.material_id == material_id)
    ).all()
    assert not connection.execute(
        select(builds.c.id).where(builds.c.material_id == material_id)
    ).all()

# 已删资料的精确作用域继续保留，外班和同班其他资料不能被补偿误删。
other = outsider.post(
    "/api/v1/materials",
    base_url=origin,
    headers={**headers, "Idempotency-Key": str(uuid4())},
    json={"title": "外班保留", "text": "外班向量不能被清理"},
)
other_id = other.json["data"]["id"]
other_build = outsider.post(
    "/api/v1/materials/" + other_id + "/index-builds",
    base_url=origin,
    headers={**headers, "Idempotency-Key": "other-class"},
    json={},
)
assert other_build.status_code == 201
with engine.connect() as connection:
    other_row = (
        connection.execute(
            select(builds).where(builds.c.id == other_build.json["data"]["id"])
        )
        .mappings()
        .one()
    )
other_scope = IndexScope(
    *(
        other_row[key]
        for key in (
            "class_id",
            "material_id",
            "source_version",
            "index_version",
            "index_config_version",
        )
    )
)
assert vectors.count(other_scope, time.monotonic() + 15) > 0
cleaner = IndexCleanupService(
    IndexCleanupRepository(engine),
    lambda collection: QdrantIndexClient(
        settings.qdrant_url, settings.qdrant_api_key, config, collection=collection
    ),
    DatabaseError,
    IndexDependencyError,
)
assert cleaner.run()["failed"] == 0
active = next(
    row
    for row in saved_builds
    if row["index_version"] == saved_material["active_index_version"]
)
deleted_scope = IndexScope(
    *(
        active[key]
        for key in (
            "class_id",
            "material_id",
            "source_version",
            "index_version",
            "index_config_version",
        )
    )
)
assert vectors.count(deleted_scope, time.monotonic() + 15) == 0
late_parts = [
    Chunk(
        row["id"],
        row["ordinal"],
        row["start_offset"],
        row["end_offset"],
        row["content"],
    )
    for row in saved_chunks
]
vectors.write(
    deleted_scope,
    late_parts,
    [[1.0] + [0.0] * 2047 for _ in late_parts],
    time.monotonic() + 15,
)
assert cleaner.run()["failed"] == 0
assert cleaner.run()["failed"] == 0
assert (
    vectors.count(deleted_scope, time.monotonic() + 15) == 0
    and vectors.count(other_scope, time.monotonic() + 15) > 0
)
assert vectors.count(other_scope, time.monotonic() + 15) > 0
assert (
    student.get("/api/v1/materials/" + material_id, base_url=origin).status_code == 404
)

# 隔离还原备份旧行，不接流量；接流量前双重放删除清单，清理凭证仍在。
repository = MaterialRepository(engine)
receipts = [
    (row["material_id"], row["deleted_at"]) for row in repository.deletion_manifest()
]
with engine.begin() as connection:
    connection.execute(insert(materials).values(saved_material))
    connection.execute(insert(bodies).values(saved_body))
    connection.execute(insert(builds), saved_builds)
    connection.execute(insert(chunks), saved_chunks)
repository.replay_deletions(receipts)
repository.replay_deletions(receipts)
assert (
    student.get(
        "/api/v1/materials/" + material_id + "/download", base_url=origin
    ).status_code
    == 404
)
assert cleaner.run()["failed"] == 0
assert vectors.count(other_scope, time.monotonic() + 15) > 0

# 有界重试：真实数据库保留失败与下次时间，第三次失败转人工。

synthetic = dict(active, index_version=10000, material_id=str(uuid4()))
with engine.begin() as connection:
    record_cleanup(connection, synthetic, service.clock())
failed_cleaner = IndexCleanupService(
    IndexCleanupRepository(engine),
    lambda collection: failing_vectors,
    DatabaseError,
    IndexDependencyError,
)


class FailingVectors:
    def count(self, scope, deadline):
        if scope.material_id == synthetic["material_id"]:
            raise IndexDependencyError("synthetic_cleanup_down")
        return vectors.count(scope, deadline)

    def delete(self, scope, deadline):
        if scope.material_id == synthetic["material_id"]:
            raise IndexDependencyError("synthetic_cleanup_down")
        return vectors.delete(scope, deadline)


failing_vectors = FailingVectors()
for attempt in range(1, 4):
    # 仅让专用故障凭证到期；其余完成凭证正常复核不应受影响。
    with engine.begin() as connection:
        connection.execute(
            update(cleanups)
            .where(cleanups.c.material_id == synthetic["material_id"])
            .values(next_attempt_at=service.clock() - timedelta(seconds=1))
        )
    local = IndexCleanupService(
        IndexCleanupRepository(engine),
        lambda collection: failing_vectors,
        DatabaseError,
        IndexDependencyError,
    )
    local.run()
    with engine.connect() as connection:
        failed_receipt = (
            connection.execute(
                select(cleanups).where(
                    cleanups.c.material_id == synthetic["material_id"]
                )
            )
            .mappings()
            .one()
        )
        assert failed_receipt["attempts"] == attempt
        assert failed_receipt["status"] == ("manual" if attempt == 3 else "retry")
        if attempt < 3:
            assert failed_receipt["next_attempt_at"] > failed_receipt["updated_at"]
assert failed_cleaner.run()["manual"] >= 1

# 本脚本只使用隔离项目集合，最终清理集合，不把替身结果记为真实网关验证。
vectors.endpoint.request("DELETE", vectors.path, None, time.monotonic() + 15)
engine.dispose()
