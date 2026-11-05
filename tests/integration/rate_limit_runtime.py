import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import Mock

from alembic import command
from alembic.config import Config
from sqlalchemy import event, inspect, select
from sqlalchemy.exc import SQLAlchemyError

from app import create_app
from app.adapters.auth_repository import AuthRepository
from app.adapters.auth_schema_v1 import accounts
from app.adapters.database import mysql_engine
from app.adapters.migrations.runner import migrate
from app.adapters.rate_limit_repository import RateLimitRepository
from app.adapters.rate_limit_schema_v3 import request_limits
from app.config import Settings
from app.services.access import AccessDenied
from app.services.rate_limits import RequestLimiter

options = dict(
    host=os.environ["MYSQL_HOST"],
    port=int(os.environ["MYSQL_PORT"]),
    database=os.environ["MYSQL_DATABASE"],
    user=os.environ["MYSQL_USER"],
    password=os.environ["MYSQL_PASSWORD"],
)
engine = mysql_engine(**options)
other_engine = mysql_engine(**options)
assert "request_limits" in inspect(engine).get_table_names()
now = datetime(2030, 1, 1, 12, 0, 30)


def fixed_database_clock(_connection, _cursor, statement, parameters, _context, _many):
    if statement.startswith("SELECT utc_timestamp("):
        return "SELECT CAST(%s AS DATETIME(6))", (now,)
    return statement, parameters


for database_engine in (engine, other_engine):
    event.listen(
        database_engine, "before_cursor_execute", fixed_database_clock, retval=True
    )
repositories = [RateLimitRepository(engine), RateLimitRepository(other_engine)]
# RL-F02：两个新主体在清理之后同时插入，清理不能锁住其索引间隙。
with engine.begin() as connection:
    connection.execute(request_limits.delete())
barrier = Barrier(2)


def wait_after_cleanup(_connection, _cursor, statement, _parameters, _context, _many):
    if statement.startswith("DELETE FROM request_limits"):
        barrier.wait(timeout=3)


for database_engine in (engine, other_engine):
    event.listen(database_engine, "after_cursor_execute", wait_after_cleanup)
try:
    with ThreadPoolExecutor(max_workers=2) as pool:
        fresh_results = list(
            pool.map(
                lambda index: repositories[index].consume(bytes([index]) * 32, 60),
                range(2),
            )
        )
    assert fresh_results == [(True, 30), (True, 30)]
finally:
    for database_engine in (engine, other_engine):
        event.remove(database_engine, "after_cursor_execute", wait_after_cleanup)

digest = sha256(b"synthetic-source").digest()
for _ in range(59):
    assert repositories[0].consume(digest, 60) == (True, 30)
with ThreadPoolExecutor(max_workers=2) as pool:
    results = list(pool.map(lambda repo: repo.consume(digest, 60)[0], repositories))
assert sorted(results) == [False, True]
assert RateLimitRepository(other_engine).consume(digest, 60) == (False, 30)
assert repositories[0].consume(sha256(b"another-source").digest(), 60) == (True, 30)
now += timedelta(seconds=30)
assert repositories[1].consume(digest, 60) == (True, 60)

# RL-N02，清理有界且当前窗口保留。
with engine.begin() as connection:
    connection.execute(
        request_limits.insert(),
        [
            {
                "scope_digest": sha256(str(number).encode()).digest(),
                "window_start": now - timedelta(minutes=5),
                "request_count": 1,
            }
            for number in range(105)
        ],
    )
repositories[0].consume(digest, 60)
with engine.connect() as connection:
    old_rows = connection.execute(
        select(request_limits).where(
            request_limits.c.window_start < now - timedelta(minutes=2)
        )
    ).all()
assert len(old_rows) == 5
repositories[0].consume(digest, 60)

# 真实 HTTP 使用不同实例和同一 MySQL 配额，超额不触发认证。
settings = Settings.load(
    {**os.environ, "APP_PUBLIC_ORIGIN": "https://campusclaw.test"},
    Path("app/BUILD_VERSION"),
)
auth = Mock()
auth.current.return_value = SimpleNamespace(
    id="synthetic-account", class_id="synthetic-class", role="teacher"
)
material_service = Mock()
material_service.create.return_value = {"id": "synthetic-material"}
auth.login.side_effect = AccessDenied(401, 1101, "账号或口令不正确")
clients = [
    create_app(
        settings,
        auth=auth,
        materials=material_service,
        limiter=RequestLimiter(repo, SQLAlchemyError),
    ).test_client()
    for repo in repositories
]
headers = {"Origin": settings.public_origin, "X-CampusClaw-Request": "same-origin"}


def login(client):
    return client.post(
        "/api/v1/auth/sessions",
        base_url=settings.public_origin,
        headers=headers,
        json={"login_name": "synthetic", "password": "synthetic"},
    )


for _ in range(60):
    assert login(clients[0]).status_code == 401
rejected = login(clients[1])
assert rejected.status_code == 429 and rejected.json["code"] == 1600
assert rejected.headers["Retry-After"] == "60" and auth.login.call_count == 60

# 登录来源额度耗尽不会耗尽账号写额度，两实例仍共享账号额度。
for _ in range(60):
    response = clients[0].post(
        "/api/v1/materials",
        base_url=settings.public_origin,
        headers={**headers, "Idempotency-Key": "synthetic-key"},
        json={"title": "title", "text": "text"},
    )
    assert response.status_code == 201
response = clients[1].post(
    "/api/v1/materials",
    base_url=settings.public_origin,
    headers={**headers, "Idempotency-Key": "synthetic-key"},
    json={"title": "title", "text": "text"},
)
assert response.status_code == 429 and material_service.create.call_count == 60

# 最后一微秒的重试等待至少一秒，新窗口恢复。
now = now.replace(second=59, microsecond=999999)
edge = sha256(b"last-microsecond").digest()
assert repositories[0].consume(edge, 1) == (True, 1)
assert repositories[1].consume(edge, 1) == (False, 1)

# 缺表失败关闭；复建后按正常配额恢复。
request_limits.drop(engine)
assert login(clients[0]).status_code == 503 and auth.login.call_count == 60
request_limits.create(engine)
assert login(clients[1]).status_code == 401

# 0002 既有数据、0003 单步降级、重升和重跑。
AuthRepository(engine).seed_demo_accounts("synthetic-unused-password-hash")
with engine.connect() as connection:
    before = connection.execute(select(accounts).order_by(accounts.c.id)).all()
config = Config()
config.set_main_option("script_location", str(Path("app/adapters/migrations")))
with engine.begin() as connection:
    config.attributes["connection"] = connection
    command.downgrade(config, "0002_materials")
assert "request_limits" not in inspect(engine).get_table_names()
migrate(engine)
migrate(engine)
with engine.connect() as connection:
    assert connection.execute(select(accounts).order_by(accounts.c.id)).all() == before
for database_engine in (engine, other_engine):
    database_engine.dispose()
print("RL-N01 RL-B01 RL-F02 RL-F03 RL-F04 RL-N02 真实共享计数、HTTP 与兼容迁移通过")
