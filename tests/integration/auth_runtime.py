import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

from sqlalchemy import event, inspect, select, update
from sqlalchemy.exc import OperationalError
from werkzeug.security import check_password_hash, generate_password_hash

from app import create_app
from app.adapters.auth_repository import AuthRepository
from app.adapters.auth_schema_v1 import accounts, classes
from app.adapters.database import mysql_engine
from app.adapters.migrations.runner import migrate
from app.api.auth import COOKIE
from app.config import Settings
from app.services.auth import AuthService, utc_now

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
expected = {"alembic_version", "classes", "accounts", "auth_sessions", "auth_audits"}
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


client = app.test_client()
assert client.get("/login", base_url=origin).status_code == 200
assert client.get(current, base_url=origin).status_code == 401
assert client.post(login, base_url=origin, json={}).status_code == 403
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
logout = winner.delete(current, base_url=origin, headers=headers)
assert logout.status_code == 200 and "Max-Age=0" in logout.headers["Set-Cookie"]
assert winner.get(current, base_url=origin).status_code == 401

assert sign_in(client).status_code == 200
assert repository.change_account(account.id, utc_now(), password_hash=first_hash)
assert client.get(current, base_url=origin).status_code == 401
assert sign_in(client).status_code == 200
assert repository.change_account(account.id, utc_now())
assert client.get(current, base_url=origin).status_code == 401
assert sign_in(client).json["code"] == 1101

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


def reject_session_insert(_conn, _cursor, statement, _parameters, _context, _many):
    if statement.startswith("INSERT INTO auth_sessions"):
        raise OperationalError(None, None, RuntimeError("synthetic insert failure"))


event.listen(engine, "before_cursor_execute", reject_session_insert)
try:
    failure = sign_in(timed_client, login_name="demo_b_student")
    assert failure.status_code == 503 and "Set-Cookie" not in failure.headers
finally:
    event.remove(engine, "before_cursor_execute", reject_session_insert)

now += timedelta(minutes=30) - timedelta(microseconds=1)
assert timed_client.get(current, base_url=origin).status_code == 200
now += timedelta(microseconds=1)
assert timed_client.get(current, base_url=origin).status_code == 401

migrate(engine, downgrade=True)
assert set(inspect(engine).get_table_names()) == {"alembic_version"}
migrate(engine, downgrade=True)
migrate(engine)
assert set(inspect(engine).get_table_names()) == expected
with engine.connect() as connection:
    assert not connection.execute(select(accounts.c.id)).all()
engine.dispose()
