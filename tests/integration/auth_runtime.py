import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock

from sqlalchemy import event, func, insert, inspect, select, update
from sqlalchemy.exc import OperationalError
from werkzeug.security import check_password_hash, generate_password_hash

from app import create_app
from app.adapters.auth_repository import AuthRepository
from app.adapters.auth_schema_v1 import accounts, auth_audits, auth_sessions, classes
from app.adapters.database import DatabaseError, mysql_engine
from app.adapters.material_repository import MaterialRepository
from app.adapters.material_schema_v2 import bodies, deletions, materials, uploads
from app.adapters.migrations.runner import migrate
from app.api.auth import COOKIE
from app.config import Settings
from app.services.auth import AuthService, utc_now
from app.services.materials import MaterialService

engine = mysql_engine(
    host=os.environ["MYSQL_HOST"],
    port=int(os.environ["MYSQL_PORT"]),
    database=os.environ["MYSQL_DATABASE"],
    user=os.environ["MYSQL_USER"],
    password=os.environ["MYSQL_PASSWORD"],
)
assert not inspect(engine).get_table_names()
migrate(engine)
migrate(engine)
expected = {
    "alembic_version",
    "classes",
    "accounts",
    "auth_sessions",
    "auth_audits",
    "materials",
    "material_bodies",
    "material_uploads",
    "material_deletions",
    "request_limits",
}
assert set(inspect(engine).get_table_names()) == expected
assert inspect(engine).get_pk_constraint("auth_sessions")["constrained_columns"] == [
    "account_id"
]
assert (
    inspect(engine).get_foreign_keys("auth_sessions")[0]["referred_table"] == "accounts"
)
assert inspect(engine).get_foreign_keys("accounts")[0]["referred_table"] == "classes"

repository = AuthRepository(engine)
password = os.environ["MYSQL_PASSWORD"]
first_hash = generate_password_hash(password, method="scrypt")
repository.seed_demo_accounts(first_hash)
with engine.begin() as connection:
    before = connection.execute(
        select(accounts.c.login_name, classes.c.code, accounts.c.role).select_from(
            accounts.join(classes)
        )
    ).all()
    assert set(before) == {
        (f"demo_{section}_{role}", f"class-{section}", role)
        for section in ("a", "b")
        for role in ("teacher", "student")
    }
    connection.execute(
        update(accounts)
        .where(accounts.c.login_name == "demo_a_teacher")
        .values(role="student")
    )
repository.seed_demo_accounts(generate_password_hash(password + "2", method="scrypt"))
account = repository.find_account("demo_a_teacher")
assert account.role == "student"
assert check_password_hash(account.password_hash, password)
with engine.connect() as connection:
    assert len(connection.execute(select(accounts.c.id)).all()) == 4
    assert len(connection.execute(select(classes.c.id)).all()) == 2

origin = "https://campusclaw.test"
settings = Settings.load(
    {**os.environ, "APP_PUBLIC_ORIGIN": origin},
    Path("app/BUILD_VERSION"),
)
app = create_app(settings)
login = "/api/v1/auth/sessions"
current = login + "/current"
headers = {"Origin": origin, "X-CampusClaw-Request": "same-origin"}


def sign_in(client, login_name="demo_a_teacher", secret=password):
    return client.post(
        login,
        base_url=origin,
        headers=headers,
        json={"login_name": login_name, "password": secret},
    )


def auth_snapshot():
    with engine.connect() as connection:
        return tuple(
            connection.execute(select(table).order_by(*table.primary_key.columns)).all()
            for table in (auth_sessions, auth_audits)
        )


client = app.test_client()
assert client.get("/login", base_url=origin).status_code == 200
assert client.get(current, base_url=origin).status_code == 401
assert client.post(login, base_url=origin, json={}).status_code == 403
initial_auth = auth_snapshot()
# AUTH-F01：参数失败不改变会话或审计。
for invalid in (
    {"login_name": "demo_a_teacher"},
    {"login_name": "demo_a_teacher", "password": False},
    {"login_name": "demo_a_teacher", "password": password, "role": "teacher"},
    {"login_name": "demo_a_teacher", "password": password, "class_id": "other"},
):
    rejected = client.post(login, base_url=origin, headers=headers, json=invalid)
    assert rejected.status_code == 400 and rejected.json["code"] == 1000
    assert "Set-Cookie" not in rejected.headers
assert auth_snapshot() == initial_auth
assert sign_in(client, secret="wrong").json["code"] == 1101
assert sign_in(client, login_name="missing").json["code"] == 1101
first = sign_in(client)
assert first.status_code == 200
assert set(first.json["data"]) == {"expires_at"}
assert all(
    flag in first.headers["Set-Cookie"]
    for flag in ("Secure", "HttpOnly", "SameSite=Strict", "Path=/")
)
assert "Domain" not in first.headers["Set-Cookie"]
assert client.get(current, base_url=origin).json["data"]["role"] == "student"

# AUTH-N01：换发只撤销该账号的旧会话。
other_accounts = {
    name: app.test_client()
    for name in ("demo_a_student", "demo_b_teacher", "demo_b_student")
}
for name, other in other_accounts.items():
    signed = sign_in(other, login_name=name)
    assert signed.status_code == 200 and signed.json["code"] == 0
renewed = sign_in(app.test_client())
assert renewed.status_code == 200 and renewed.json["code"] == 0
assert client.get(current, base_url=origin).json["code"] == 1100
for other in other_accounts.values():
    assert other.get(current, base_url=origin).json["code"] == 0


def concurrent_sign_in(_):
    other = app.test_client()
    assert sign_in(other).status_code == 200
    return other


with ThreadPoolExecutor(max_workers=2) as pool:
    contenders = list(pool.map(concurrent_sign_in, range(2)))
statuses = [other.get(current, base_url=origin).status_code for other in contenders]
assert sorted(statuses) == [200, 401]
assert client.delete(current, base_url=origin, headers=headers).status_code == 401
winner = contenders[statuses.index(200)]
assert winner.get_cookie(COOKIE, domain="campusclaw.test") is not None
assert (
    winner.delete(
        current,
        base_url=origin,
        headers={
            **headers,
            "Origin": "https://other.campusclaw.test",
        },
    ).status_code
    == 403
)
assert winner.get(current, base_url=origin).status_code == 200
revoked_cookie = winner.get_cookie(COOKIE, domain="campusclaw.test").value
logout = winner.delete(current, base_url=origin, headers=headers)
assert logout.status_code == 200 and "Max-Age=0" in logout.headers["Set-Cookie"]
assert winner.get(current, base_url=origin).status_code == 401
before = auth_snapshot()
assert winner.delete(current, base_url=origin, headers=headers).status_code == 401
assert auth_snapshot() == before

assert sign_in(client).status_code == 200
assert repository.change_account(account.id, utc_now(), password_hash=first_hash)
assert client.get(current, base_url=origin).status_code == 401
assert sign_in(client).status_code == 200
assert repository.change_account(account.id, utc_now())
assert client.get(current, base_url=origin).status_code == 401
assert sign_in(client).json["code"] == 1101

# AUTH-F02：三条公开失败响应同构，且每条路径实际校验口令哈希。
verify_password = Mock(wraps=check_password_hash)
enum_app = create_app(
    settings,
    auth=AuthService(repository, verify_password, first_hash, DatabaseError),
)
before = auth_snapshot()
credential_errors = []
for name, secret in (
    ("demo_a_student", "wrong"),
    ("demo_a_teacher", password),
    ("missing", password),
):
    rejected = sign_in(enum_app.test_client(), login_name=name, secret=secret)
    assert rejected.status_code == 401 and rejected.json["code"] == 1101
    assert "Set-Cookie" not in rejected.headers
    credential_errors.append((rejected.json["message"], rejected.json["data"]))
assert credential_errors[0] == credential_errors[1] == credential_errors[2]
assert verify_password.call_count == 3 and auth_snapshot() == before

now = utc_now()
timed_auth = AuthService(
    repository,
    check_password_hash,
    first_hash,
    OperationalError,
    clock=lambda: now,
)
timed_app = create_app(settings, auth=timed_auth)
timed_client = timed_app.test_client()
assert sign_in(timed_client, login_name="demo_b_student").status_code == 200


def reject_account_query(_conn, _cursor, statement, _parameters, _context, _many):
    if statement.startswith("SELECT ") and "WHERE accounts.login_name =" in statement:
        raise OperationalError(
            None, None, RuntimeError("synthetic account read failure")
        )


def reject_session_insert(_conn, _cursor, statement, _parameters, _context, _many):
    if statement.startswith("INSERT INTO auth_sessions"):
        raise OperationalError(None, None, RuntimeError("synthetic insert failure"))


# AUTH-F04：查询及事务内失败均保留原有效会话。
before = auth_snapshot()
for hook in (reject_account_query, reject_session_insert):
    event.listen(engine, "before_cursor_execute", hook)
    try:
        failure = sign_in(timed_client, login_name="demo_b_student")
        assert failure.status_code == 503 and failure.json["code"] == 1500
        assert "Set-Cookie" not in failure.headers
        assert timed_client.get(current, base_url=origin).status_code == 200
        assert auth_snapshot() == before
    finally:
        event.remove(engine, "before_cursor_execute", hook)

now += timedelta(minutes=30) - timedelta(microseconds=1)
assert timed_client.get(current, base_url=origin).status_code == 200
now += timedelta(microseconds=1)
assert timed_client.get(current, base_url=origin).status_code == 401
expired_api = timed_client.get("/api/v1/materials", base_url=origin)
assert expired_api.status_code == 401 and expired_api.json["code"] == 1100
expired_page = timed_client.get("/materials", base_url=origin)
assert expired_page.status_code == 303
assert expired_page.location.startswith("/login?next=/materials")


# CA-02/03/04，真实 Cookie、MySQL、同班与跨班副作用。
repo = MaterialRepository(engine)
material_app = create_app(
    settings,
    auth=AuthService(repository, check_password_hash, first_hash, DatabaseError),
    materials=MaterialService(repo, DatabaseError),
)
teacher, peer, outsider, anonymous = [material_app.test_client() for _ in range(4)]
temp_directory = tempfile.TemporaryDirectory()
tempfile.tempdir = temp_directory.name
with engine.begin() as connection:
    connection.execute(
        update(accounts)
        .where(accounts.c.login_name == "demo_a_teacher")
        .values(role="teacher", enabled=True)
    )
assert sign_in(teacher).status_code == 200
assert sign_in(peer, login_name="demo_a_student").status_code == 200
assert sign_in(outsider, login_name="demo_b_teacher").status_code == 200

materials_url = "/api/v1/materials"


def upload_text(actor, key, text="正文"):
    return actor.post(
        materials_url,
        base_url=origin,
        headers={**headers, "Idempotency-Key": key},
        json={"title": "资料", "text": text},
    )


def upload_file(actor, key, raw, name="source.md", media="text/markdown", **fields):
    return actor.post(
        materials_url,
        base_url=origin,
        headers={**headers, "Idempotency-Key": key},
        data={"title": "原文", "file": (BytesIO(raw), name, media), **fields},
    )


def snapshot():
    assert not list(Path(temp_directory.name).iterdir())
    with engine.connect() as connection:
        return tuple(
            connection.scalar(select(func.count()).select_from(table))
            for table in (materials, bodies, uploads, deletions)
        )


redirected = anonymous.get("/console", base_url=origin)
assert redirected.status_code == 303 and redirected.location.startswith(
    "/login?next=/console"
)
assert anonymous.get(materials_url, base_url=origin).status_code == 401
assert teacher.get("/console", base_url=origin).status_code == 200
assert peer.get("/console", base_url=origin).status_code == 403
assert peer.get("/materials", base_url=origin).status_code == 200
assert anonymous.get(materials_url + "/missing", base_url=origin).json["code"] == 1100
assert peer.get(materials_url + "/bad-id", base_url=origin).json["code"] == 1000
assert anonymous.get("/unknown", base_url=origin).status_code == 404
assert peer.put(materials_url, base_url=origin).status_code == 405

before = snapshot()
# ACL-F02/F04 与 ING-F01：拒绝非法或越权写入并保留存储快照。
assert upload_text(peer, "denied").status_code == 403
assert upload_file(peer, "denied-file", b"text").status_code == 403
assert upload_text(teacher, "invalid", " \x00").status_code == 400
assert upload_text(teacher, "blank", "  ").status_code == 400
assert upload_text(teacher, "large", "x" * 1048577).status_code == 400
assert upload_file(teacher, "large-file", b"x" * 1048577).status_code == 400
for filename, media, raw in (
    ("../a.txt", "text/plain", b"text"),
    ("/a.txt", "text/plain", b"text"),
    ("a.pdf", "application/octet-stream", b"text"),
    ("a.txt", "text/html", b"text"),
    ("a.md", "text/markdown", b"\xff"),
):
    file_rejection = teacher.post(
        materials_url,
        base_url=origin,
        headers={**headers, "Idempotency-Key": "invalid-file"},
        data={"title": "资料", "file": (BytesIO(raw), filename, media)},
    )
    assert file_rejection.status_code == 400 and file_rejection.json["code"] == 1000
assert (
    teacher.get(materials_url + "?class_id=other", base_url=origin).status_code == 400
)
for field in ("class_id", "role"):
    forged_rejection = teacher.post(
        materials_url,
        base_url=origin,
        headers={**headers, "Idempotency-Key": "forged-identity"},
        json={"title": "资料", "text": "原文", field: "other"},
    )
    assert forged_rejection.status_code == 400 and forged_rejection.json["code"] == 1000
assert upload_file(teacher, "mixed", b"text", text="正文").status_code == 400
assert snapshot() == before

for invalid_cookie in (None, "bad", "a" * 43, revoked_cookie):
    forged = material_app.test_client()
    if invalid_cookie is not None:
        forged.set_cookie(COOKIE, invalid_cookie, domain="campusclaw.test")
    rejected = forged.get(
        materials_url,
        base_url=origin,
        headers={"Authorization": "Bearer invalid", "X-Role": "teacher"},
    )
    assert rejected.status_code == 401 and rejected.json["code"] == 1100
    assert rejected.json["data"] is None


def reject_body_insert(connection, _cursor, statement, _parameters, _context, _many):
    if statement.startswith("INSERT INTO material_bodies"):
        assert (
            connection.scalar(select(func.count()).select_from(materials))
            == before[0] + 1
        )
        assert snapshot() == before
        raise OperationalError(None, None, RuntimeError("synthetic body failure"))


event.listen(engine, "before_cursor_execute", reject_body_insert)
try:
    # ING-F02：上传合法文件，故障点位于元数据和正文写入之间。
    failed = upload_file(teacher, "atomic", b"x" * 1048576)
    assert failed.status_code == 503 and failed.json["code"] == 1500
    assert snapshot() == before
finally:
    event.remove(engine, "before_cursor_execute", reject_body_insert)

cookie = teacher.get_cookie(COOKIE, domain="campusclaw.test")


def concurrent_upload(_):
    worker = material_app.test_client()
    worker.set_cookie(COOKIE, cookie.value, domain="campusclaw.test")
    result = upload_file(worker, "atomic", b"x" * 1048576)
    assert result.status_code == 201 and result.json["code"] == 0
    assert result.json["data"]["original_only"] is True
    return result


with ThreadPoolExecutor(max_workers=2) as pool:
    retried, repeated = pool.map(concurrent_upload, range(2))
assert retried.json["data"] == repeated.json["data"]
assert retried.json["request_id"] != repeated.json["request_id"]
assert snapshot() == (1, 1, 1, 0)
at_capacity = upload_text(teacher, "parallel", "x" * 32000)
assert (
    at_capacity.status_code == 201
    and at_capacity.json["data"]["original_only"] is False
)
assert snapshot() == (2, 2, 2, 0)
assert upload_text(teacher, "parallel", "changed").status_code == 409


def reject_material_store(_conn, _cursor, statement, _parameters, _context, _many):
    if statement.startswith("INSERT INTO materials"):
        raise OperationalError(None, None, RuntimeError("synthetic store unavailable"))


# ING-F03：身份解析成功，资料持久层不可用。
before = snapshot()
event.listen(engine, "before_cursor_execute", reject_material_store)
try:
    storage_unavailable = upload_text(teacher, "storage-failure")
    assert (
        storage_unavailable.status_code == 503
        and storage_unavailable.json["code"] == 1500
    )
    assert storage_unavailable.json["data"] is None
finally:
    event.remove(engine, "before_cursor_execute", reject_material_store)
assert snapshot() == before


class UncertainCommitRepository(MaterialRepository):
    @contextmanager
    def transaction(self):
        with super().transaction() as connection:
            yield connection
        raise OperationalError(None, None, RuntimeError("synthetic lost response"))


uncertain_app = create_app(
    settings,
    materials=MaterialService(UncertainCommitRepository(engine), DatabaseError),
)
uncertain_client = uncertain_app.test_client()
uncertain_client.set_cookie(COOKIE, cookie.value, domain="campusclaw.test")
lost_response = upload_text(uncertain_client, "lost", "x" * 32001)
assert lost_response.status_code == 503
recovered = upload_text(teacher, "lost", "x" * 32001)
assert recovered.status_code == 201 and recovered.json["data"]["original_only"] is True
assert recovered.json["data"]["character_count"] == 32001
recovered_url = materials_url + "/" + recovered.json["data"]["id"]
assert peer.get(recovered_url + "/download", base_url=origin).data == b"x" * 32001
assert snapshot() == (3, 3, 3, 0)

raw = b"\xef\xbb\xbf<script>alert(1)</script>\r\n"
created = teacher.post(
    materials_url,
    base_url=origin,
    headers={**headers, "Idempotency-Key": "file"},
    data={"title": "原文", "file": (BytesIO(raw), "source.md", "text/markdown")},
)
assert created.status_code == 201
target = materials_url + "/" + created.json["data"]["id"]
assert peer.get(target, base_url=origin).json["data"]["text"] == raw.decode("utf-8-sig")
attachment = peer.get(target + "/download", base_url=origin)
assert attachment.data == raw and attachment.status_code == 200
assert attachment.headers["Content-Type"] == "application/octet-stream"
assert attachment.headers["X-Content-Type-Options"] == "nosniff"
assert attachment.headers["Content-Disposition"] == (
    "attachment; filename=" + created.json["data"]["id"] + ".md"
)
missing = materials_url + "/00000000-0000-0000-0000-000000000000"
for suffix in ("", "/download"):
    actual = outsider.get(target + suffix, base_url=origin)
    absent = outsider.get(missing + suffix, base_url=origin)
    assert actual.status_code == absent.status_code == 404
    assert {k: v for k, v in actual.json.items() if k != "request_id"} == {
        k: v for k, v in absent.json.items() if k != "request_id"
    }
    assert "Content-Disposition" not in actual.headers

# ACL-B01：B 班学生空列表，A 班排序相同的行跨页稳定。
b_student = material_app.test_client()
assert sign_in(b_student, login_name="demo_b_student").status_code == 200
empty = b_student.get(materials_url, base_url=origin)
assert empty.status_code == 200 and empty.json["data"]["total"] == 0
assert empty.json["data"]["items"] == []
page_ids = []
for page in range(1, 5):
    listing = peer.get(
        materials_url, base_url=origin, query_string={"page": page, "page_size": 1}
    ).json["data"]
    assert len(listing["items"]) == 1 and listing["total"] == 4
    page_ids.append(listing["items"][0]["id"])
assert page_ids == sorted(
    {
        retried.json["data"]["id"],
        at_capacity.json["data"]["id"],
        recovered.json["data"]["id"],
        created.json["data"]["id"],
    }
)

# ACL-N01/F01/F03：双班双角色读写配对，跨班响应与缺失同构。
other_material = upload_text(outsider, "b-class", "B 班独立原文")
assert other_material.status_code == 201
other_id = other_material.json["data"]["id"]
other_url = materials_url + "/" + other_id
for actor, expected_ids, detail in (
    (teacher, set(page_ids), target),
    (peer, set(page_ids), target),
    (outsider, {other_id}, other_url),
    (b_student, {other_id}, other_url),
):
    result = actor.get(materials_url, base_url=origin)
    assert result.status_code == 200 and result.json["code"] == 0
    assert {item["id"] for item in result.json["data"]["items"]} == expected_ids
    assert result.json["data"]["total"] == len(expected_ids)
    assert actor.get(detail, base_url=origin).json["code"] == 0
for actor in (teacher, peer):
    for suffix in ("", "/download"):
        actual = actor.get(other_url + suffix, base_url=origin)
        absent = actor.get(missing + suffix, base_url=origin)
        assert actual.status_code == absent.status_code == 404
        assert actual.json["code"] == absent.json["code"] == 1300
        assert actual.json["message"] == absent.json["message"]
        assert actual.json["data"] is absent.json["data"] is None
        assert "Content-Disposition" not in actual.headers
for path in (materials_url, target, target + "/download"):
    rejected = anonymous.get(path, base_url=origin)
    assert rejected.status_code == 401 and rejected.json["code"] == 1100
    assert (
        rejected.json["data"] is None and "Content-Disposition" not in rejected.headers
    )
assert anonymous.get("/static/source.md", base_url=origin).status_code == 404
revision = {"revision": 1, "sort_order": 3, "title": "更新标题"}
assert (
    outsider.patch(target, base_url=origin, headers=headers, json=revision).status_code
    == 404
)
assert (
    peer.patch(target, base_url=origin, headers=headers, json=revision).status_code
    == 403
)
updated = teacher.patch(target, base_url=origin, headers=headers, json=revision)
assert updated.status_code == 200 and updated.json["data"]["revision"] == 2
assert updated.json["data"]["id"] == created.json["data"]["id"]
assert updated.json["data"]["content_version"] == 1
assert (
    updated.json["data"]["sort_order"] == 3
    and updated.json["data"]["title"] == "更新标题"
)
assert peer.get(target + "/download", base_url=origin).data == raw
assert (
    teacher.patch(target, base_url=origin, headers=headers, json=revision).status_code
    == 409
)
assert peer.delete(target, base_url=origin, headers=headers).status_code == 403
assert outsider.delete(target, base_url=origin, headers=headers).status_code == 404
invalid_download = teacher.get(materials_url + "/bad-id/download", base_url=origin)
assert invalid_download.status_code == 400 and invalid_download.json["code"] == 1000
assert "Content-Disposition" not in invalid_download.headers
before = snapshot()
for method, body in (("PATCH", {"json": revision}), ("DELETE", {})):
    cross = teacher.open(
        other_url, method=method, base_url=origin, headers=headers, **body
    )
    absent = teacher.open(
        missing, method=method, base_url=origin, headers=headers, **body
    )
    assert cross.status_code == absent.status_code == 404
    assert cross.json["code"] == absent.json["code"] == 1300
    assert cross.json["message"] == absent.json["message"]
    assert cross.json["data"] is absent.json["data"] is None
assert snapshot() == before
assert outsider.get(other_url, base_url=origin).json["data"]["revision"] == 1


def reject_body_read(_conn, _cursor, statement, _parameters, _context, _many):
    if statement.startswith("SELECT ") and "JOIN material_bodies" in statement:
        raise OperationalError(None, None, RuntimeError("synthetic read failure"))


event.listen(engine, "before_cursor_execute", reject_body_read)
try:
    unavailable = peer.get(target + "/download", base_url=origin)
    assert unavailable.status_code == 503 and unavailable.json["code"] == 1500
    assert "Content-Disposition" not in unavailable.headers
finally:
    event.remove(engine, "before_cursor_execute", reject_body_read)

target_id = created.json["data"]["id"]
with engine.connect() as connection:
    old_material = dict(
        connection.execute(select(materials).where(materials.c.id == target_id))
        .mappings()
        .one()
    )
    old_upload = dict(
        connection.execute(select(uploads).where(uploads.c.material_id == target_id))
        .mappings()
        .one()
    )


def reject_metadata_delete(_conn, _cursor, statement, _parameters, _context, _many):
    if statement.startswith("DELETE FROM materials"):
        raise OperationalError(None, None, RuntimeError("synthetic delete failure"))


before = snapshot()
event.listen(engine, "before_cursor_execute", reject_metadata_delete)
try:
    assert teacher.delete(target, base_url=origin, headers=headers).status_code == 503
    assert snapshot() == before
    assert peer.get(target + "/download", base_url=origin).data == raw
finally:
    event.remove(engine, "before_cursor_execute", reject_metadata_delete)
assert teacher.delete(target, base_url=origin, headers=headers).status_code == 200
assert teacher.delete(target, base_url=origin, headers=headers).status_code == 404
assert peer.get(target, base_url=origin).status_code == 404
assert peer.get(target + "/download", base_url=origin).status_code == 404
assert upload_file(teacher, "file", raw).status_code == 409
assert peer.get(recovered_url + "/download", base_url=origin).status_code == 200
remaining = peer.get(materials_url, base_url=origin).json["data"]["items"]
assert {item["id"] for item in remaining} == set(page_ids) - {target_id}

receipts = [(row["material_id"], row["deleted_at"]) for row in repo.deletion_manifest()]
assert len(receipts) == 1 and receipts[0][0] == target_id
# 还原备份中的旧行，再重放独立保存的删除凭证。
with engine.begin() as connection:
    connection.execute(deletions.delete().where(deletions.c.material_id == target_id))
    connection.execute(uploads.delete().where(uploads.c.material_id == target_id))
    connection.execute(insert(materials).values(old_material))
    connection.execute(insert(bodies).values(material_id=target_id, content=raw))
    connection.execute(insert(uploads).values(old_upload))
repo.replay_deletions(receipts)
repo.replay_deletions(receipts)
assert peer.get(target + "/download", base_url=origin).status_code == 404
assert snapshot() == (4, 4, 5, 1)
with engine.begin() as connection:
    connection.execute(
        update(accounts)
        .where(accounts.c.login_name == "demo_a_teacher")
        .values(role="student")
    )
before = snapshot()
assert upload_text(teacher, "downgraded").status_code == 403
assert snapshot() == before


def reject_current_identity(_conn, _cursor, statement, _parameters, _context, _many):
    if (
        statement.startswith("SELECT ")
        and "JOIN accounts" in statement
        and "auth_sessions.token_digest =" in statement
    ):
        raise OperationalError(
            None, None, RuntimeError("synthetic identity unavailable")
        )


# ACL-F05：当前身份查询故障时失败关闭。
event.listen(engine, "before_cursor_execute", reject_current_identity)
try:
    rejected = teacher.get(materials_url, base_url=origin)
    assert rejected.status_code == 503 and rejected.json["code"] == 1500
    assert rejected.json["data"] is None
finally:
    event.remove(engine, "before_cursor_execute", reject_current_identity)
assert snapshot() == before

# AUTH-N02：分别对三个已登录账号注销、改密和停用。
peer_id = peer.get(current, base_url=origin).json["data"]["id"]
outsider_id = outsider.get(current, base_url=origin).json["data"]["id"]
assert teacher.delete(current, base_url=origin, headers=headers).json["code"] == 0
assert repository.change_account(peer_id, utc_now(), password_hash=first_hash)
assert repository.change_account(outsider_id, utc_now())
for actor in (teacher, peer, outsider):
    rejected = actor.get(current, base_url=origin)
    assert rejected.status_code == 401 and rejected.json["code"] == 1100

migrate(engine, downgrade=True)
assert set(inspect(engine).get_table_names()) == {"alembic_version"}
migrate(engine, downgrade=True)
migrate(engine)
assert set(inspect(engine).get_table_names()) == expected
with engine.connect() as connection:
    assert not connection.execute(select(accounts.c.id)).all()
engine.dispose()
tempfile.tempdir = None
temp_directory.cleanup()
