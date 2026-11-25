"""DAB-N02：真实 MySQL、固定预算窗口、并发拒绝与合法教学副作用。"""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path
from statistics import quantiles
from threading import Event, Lock
from time import monotonic
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import event, func, select
from sqlalchemy.engine import Engine
from werkzeug.security import generate_password_hash

import app as campus
from app.adapters.assistant_schema_v8 import skills, templates
from app.adapters.auth_repository import AuthRepository
from app.adapters.auth_schema_v1 import accounts
from app.adapters.database import mysql_engine
from app.adapters.migrations.runner import migrate
from app.adapters.operation_audit_schema_v13 import events
from app.adapters.teaching_schema_v10 import quiz_results
from app.api.auth import COOKIE
from app.config import Settings
from app.services.denied_audit_budget import DeniedAuditBudget

origin = "https://campusclaw.test"
headers = {"Origin": origin, "X-CampusClaw-Request": "same-origin"}
engine = mysql_engine(
    host=os.environ["MYSQL_HOST"],
    port=int(os.environ["MYSQL_PORT"]),
    database=os.environ["MYSQL_DATABASE"],
    user=os.environ["MYSQL_USER"],
    password=os.environ["MYSQL_PASSWORD"],
)
migrate(engine)
AuthRepository(engine).seed_demo_accounts(
    generate_password_hash(os.environ["MYSQL_PASSWORD"], method="scrypt")
)
settings = replace(
    Settings.load(
        os.environ | {"APP_PUBLIC_ORIGIN": origin}, Path("app/BUILD_VERSION")
    ),
    audit_denied_subject_limit=2,
    audit_denied_global_limit=3,
)
# 只固定预算时钟，HTTP、认证、授权、数据库与教学业务使用真实实现。
with patch.object(
    campus, "DeniedAuditBudget", partial(DeniedAuditBudget, clock=lambda: 0)
):
    app = campus.create_app(settings)


def call(client, method, path, payload=None, extra=None):
    return client.open(
        path,
        method=method,
        base_url=origin,
        headers=headers | (extra or {}),
        **({"json": payload} if payload is not None else {}),
    )


def checked(client, method, path, payload=None, status=200, extra=None):
    response = call(client, method, path, payload, extra)
    assert response.status_code == status and response.json["code"] == 0, (
        path,
        response.status_code,
    )
    return response.json["data"]


def login(name):
    client = app.test_client()
    checked(
        client,
        "POST",
        "/api/v1/auth/sessions",
        {"login_name": name, "password": os.environ["MYSQL_PASSWORD"]},
    )
    return client


teacher, student_a, student_b = [
    login(name) for name in ("demo_a_teacher", "demo_a_student", "demo_b_student")
]
source = checked(
    teacher,
    "POST",
    "/api/v1/materials",
    {"title": "预算回归讲义", "text": "合成材料"},
    201,
)
question = checked(
    teacher,
    "POST",
    "/api/v1/questions",
    {
        "kind": "single_choice",
        "stem": "合成问题",
        "options": ["甲", "乙"],
        "answer": "A",
        "explanation": "合成解析",
    },
    201,
)
checked(
    teacher,
    "POST",
    f"/api/v1/questions/{question['id']}/reviews",
    {"expected_version": 1},
)
now = datetime.now(UTC)
quiz = checked(
    teacher,
    "POST",
    "/api/v1/quizzes",
    {
        "title": "预算回归测验",
        "chapter_id": None,
        "deadline_at": (now + timedelta(hours=1)).isoformat(),
        "answers_open_at": (now + timedelta(hours=2)).isoformat(),
        "items": [{"question_id": question["id"], "points": 5}],
    },
    201,
)
checked(teacher, "POST", f"/api/v1/quizzes/{quiz['id']}/publications", {})
item = checked(student_a, "GET", f"/api/v1/quizzes/{quiz['id']}")["items"][0]["id"]


def snapshot():
    with engine.connect() as connection:
        return [
            connection.execute(select(table).order_by(*table.primary_key.columns)).all()
            for table in (skills, templates)
        ]


before = snapshot()
with engine.connect() as connection:
    actor_ids = connection.scalars(
        select(accounts.c.id).where(
            accounts.c.login_name.in_(["demo_a_student", "demo_b_student"])
        )
    ).all()
    existing = connection.scalar(
        select(func.count())
        .select_from(events)
        .where(events.c.outcome == "denied", events.c.actor_id.in_(actor_ids))
    )
assert existing == 0


def reads(client, count):
    timings = []
    for _ in range(count):
        started = monotonic()
        response = call(client, "GET", f"/api/v1/materials/{source['id']}")
        timings.append((monotonic() - started) * 1000)
        assert (
            response.status_code == 200 and response.json["data"]["text"] == "合成材料"
        )
    return timings


baseline = reads(student_a, 20)
ready = Event()
audit_attempts = [0]
attempt_lock = Lock()


def count_audits(_connection, _cursor, statement, _parameters, _context, _many):
    if statement.startswith("INSERT INTO operation_audit_events"):
        with attempt_lock:
            audit_attempts[0] += 1


# 应用使用自己的 engine；在同一进程全局连接事件观察真实 INSERT。
event.listen(Engine, "before_cursor_execute", count_audits)


def attack(cookie):
    client = app.test_client()
    client.set_cookie(COOKIE, cookie, domain="campusclaw.test", secure=True)
    ready.wait()
    timings = []
    for _ in range(100):
        started = monotonic()
        response = call(
            client,
            "PATCH",
            f"/api/v1/skills/{uuid4()}",
            {"name": "拒绝写入", "revision": 1},
        )
        timings.append((monotonic() - started) * 1000)
        assert response.status_code == 403 and response.json["code"] == 1200
        assert response.json["data"] is None
    return timings


def normal():
    ready.wait()
    timings = reads(student_a, 20)
    saved = checked(
        student_a,
        "PUT",
        f"/api/v1/quizzes/{quiz['id']}/draft",
        {"draft_revision": 0, "answers": {item: "A"}},
    )
    submitted = checked(
        student_a,
        "POST",
        f"/api/v1/quizzes/{quiz['id']}/submissions",
        {"draft_revision": saved["revision"], "answers": {item: "A"}},
        201,
        {"Idempotency-Key": "denied-budget-submit"},
    )
    return timings, submitted["submission_id"]


try:
    with ThreadPoolExecutor(max_workers=3) as pool:
        attacks = [
            pool.submit(
                attack, client.get_cookie(COOKIE, domain="campusclaw.test").value
            )
            for client in (student_a, student_b)
        ]
        healthy = pool.submit(normal)
        ready.set()
        attack_times = [timing for future in attacks for timing in future.result()]
        normal_times, submission_id = healthy.result()
finally:
    event.remove(Engine, "before_cursor_execute", count_audits)

assert before == snapshot()
with engine.connect() as connection:
    denial_rows = connection.execute(
        select(events.c.actor_id, func.count())
        .where(events.c.outcome == "denied", events.c.actor_id.in_(actor_ids))
        .group_by(events.c.actor_id)
    ).all()
    score = connection.scalar(
        select(quiz_results.c.score).where(
            quiz_results.c.submission_id == submission_id
        )
    )
assert sum(row[1] for row in denial_rows) == 3
assert all(row[1] <= 2 for row in denial_rows)
assert audit_attempts[0] == 3
assert score == 5
p95 = quantiles(normal_times, n=20)[18]
assert p95 < 1000
print(
    json.dumps(
        {
            "rejected_requests": len(attack_times),
            "audit_insert_attempts": audit_attempts[0],
            "audit_rows": 3,
            "legitimate_reads": len(normal_times),
            "baseline_read_p95_ms": round(quantiles(baseline, n=20)[18], 2),
            "loaded_read_p95_ms": round(p95, 2),
            "legitimate_errors": 0,
            "persisted_score": score,
            "budget_window": "fixed-test-clock",
        }
    )
)
print("denied_audit_runtime_ok")
