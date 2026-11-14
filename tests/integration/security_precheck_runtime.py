"""第 8 课合成班级的权限对照、写入副作用及技能审计。"""

import json
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from session_proxy_worker import install
from sqlalchemy import event, insert, inspect, select
from sqlalchemy.exc import OperationalError
from werkzeug.security import generate_password_hash

from app import create_app
from app.adapters.assistant_schema_v8 import (
    assistant_revisions,
    assistants,
    audits,
    runs,
    skill_revisions,
    skills,
    template_revisions,
    templates,
)
from app.adapters.auth_repository import AuthRepository
from app.adapters.auth_schema_v1 import accounts
from app.adapters.database import mysql_engine
from app.adapters.migrations.runner import migrate
from app.adapters.operation_audit_schema_v13 import events
from app.adapters.teaching_schema_v10 import quiz_results, quiz_submissions
from app.adapters.teaching_schema_v12 import jobs, outbox
from app.config import ChatSettings, Settings
from app.services.auth import utc_now

origin = "https://campusclaw.test"
headers = {"Origin": origin, "X-CampusClaw-Request": "same-origin"}
database = os.environ["MYSQL_DATABASE"]
assert database.startswith("campusclaw_test_")
engine = mysql_engine(
    host=os.environ["MYSQL_HOST"],
    port=int(os.environ["MYSQL_PORT"]),
    database=database,
    user=os.environ["MYSQL_USER"],
    password=os.environ["MYSQL_PASSWORD"],
)
migrate(engine)
password = uuid4().hex
AuthRepository(engine).seed_demo_accounts(
    generate_password_hash(password, method="scrypt")
)
settings = Settings.load(
    os.environ | {"APP_PUBLIC_ORIGIN": origin}, Path("app/BUILD_VERSION")
)
app = create_app(settings)


def call(client, method, path, payload=None):
    options = {
        "headers": headers | {"Idempotency-Key": uuid4().hex},
        "base_url": origin,
    }
    if payload is not None:
        options["json"] = payload
    return client.open(path, method=method, **options)


def checked(client, method, path, payload=None, status=200):
    response = call(client, method, path, payload)
    assert response.status_code == status, (method, path, response.status_code)
    return response.json["data"]


def login(name):
    client = app.test_client()
    checked(
        client,
        "POST",
        "/api/v1/auth/sessions",
        {"login_name": "demo_" + name, "password": password},
    )
    return client


def actor(name):
    with engine.connect() as connection:
        return connection.execute(
            select(accounts.c.id, accounts.c.class_id).where(
                accounts.c.login_name == "demo_" + name
            )
        ).one()


def snapshot(*tables):
    with engine.connect() as connection:
        return [
            connection.execute(select(table).order_by(*table.primary_key.columns)).all()
            for table in tables
        ]


def envelope(response):
    return (
        response.status_code,
        response.json["code"],
        response.json["message"],
        response.json["data"],
    )


teacher, student, other_teacher, other_student = [
    login(name) for name in ("a_teacher", "a_student", "b_teacher", "b_student")
]
a, b = actor("a_teacher"), actor("b_teacher")
a1 = actor("a_student")
assert a.class_id != b.class_id
source_a, source_b = "蓝鲸动力站的额定电压为24伏。", "海豚实验室的仪表读数为50赫兹。"
materials = [
    checked(
        client,
        "POST",
        "/api/v1/materials",
        {"title": "合成讲义", "text": source},
        status=201,
    )["id"]
    for client, source in ((teacher, source_a), (other_teacher, source_b))
]
app = create_app(
    replace(
        settings,
        chat=ChatSettings(
            "https://ai-gateway.devops.hello1023.com/v1",
            "synthetic-model-credential",
            "course-chat",
        ),
    )
)
model_client = app.extensions["private_sessions"].ai.chat
assist_id, skill_id = install(
    app, engine, a.class_id, a.id, materials[0], text=source_a
)
install(create_app(settings), engine, b.class_id, b.id, materials[1], text=source_b)
teacher, student, other_teacher, other_student = [
    login(name) for name in ("a_teacher", "a_student", "b_teacher", "b_student")
]

for client, identifier in zip((student, other_student), materials, strict=True):
    checked(client, "GET", f"/api/v1/materials/{identifier}")

search_path = "/api/v1/searches"
search_a = {"query": "蓝鲸", "mode": "keyword"}
search_b = {"query": "海豚", "mode": "keyword"}
a_hits = checked(student, "POST", search_path, search_a)["items"]
b_hits = checked(other_student, "POST", search_path, search_b)["items"]
assert len(a_hits) == len(b_hits) == 1
cross_hits = checked(other_student, "POST", search_path, search_a)["items"]
foreign = envelope(call(student, "GET", f"/api/v1/materials/{materials[1]}"))
missing = envelope(call(student, "GET", f"/api/v1/materials/{uuid4()}"))

anonymous = app.test_client()
material_path = "/api/v1/materials/" + materials[0]
protected = [
    ("GET", "/api/v1/auth/sessions/current", "/api/v1/auth/sessions/current", None),
    ("GET", "/api/v1/materials", "/api/v1/materials", None),
    ("GET", material_path, "/api/v1/materials/{id}", None),
    ("GET", material_path + "/download", "/api/v1/materials/{id}/download", None),
    ("POST", search_path, search_path, search_a),
]
anon_results = []
for method, path, public_path, payload in protected:
    assert call(student, method, path, payload).status_code == 200
    response = call(anonymous, method, path, payload)
    body = response.get_json(silent=True) or {}
    anon_results.append(
        [
            method,
            public_path,
            response.status_code,
            body.get("code"),
            "data" in body and body["data"] is None,
        ]
    )

template = {
    "name": "合成练习模板",
    "app_key": "practice",
    "prompt": "{{input}}",
    "enabled": True,
}
template_id = checked(
    teacher, "POST", "/api/v1/prompt-templates", template, status=201
)["id"]
skill = {
    "name": "课末合成技能",
    "conditions": ["蓝鲸"],
    "enabled": True,
    "tools": [],
    "steps": [{"type": "model", "instruction": "基于授权资料回答。"}],
}
assistant = {
    "name": "课末合成助手",
    "prompt": "",
    "enabled": True,
    "material_ids": [materials[0]],
    "skill_ids": [skill_id],
}
config_results = []
denial_requests = []
for segment, identifier, payload in (
    ("skills", skill_id, skill),
    (
        "prompt-templates",
        template_id,
        {key: template[key] for key in ("name", "prompt", "enabled")},
    ),
    ("assistants", assist_id, assistant),
):
    path = f"/api/v1/{segment}/{identifier}"
    changed = checked(teacher, "PATCH", path, payload | {"revision": 1})
    assert changed["revision"] == 2
    tables = (
        skills,
        skill_revisions,
        templates,
        template_revisions,
        assistants,
        assistant_revisions,
        audits,
    )
    before = snapshot(*tables)
    rejected = call(
        student,
        "PATCH",
        path,
        payload | {"revision": 2, "name": "学生尝试的合成名称"},
    )
    denied = envelope(rejected)
    denial_requests.append(rejected.headers["X-Request-ID"])
    config_results.append([segment, denied[0], denied[1], before == snapshot(*tables)])

quiz_question = {
    "kind": "single_choice",
    "stem": "甲乙选一项",
    "options": ["甲", "乙"],
    "answer": "A",
    "explanation": "合成未开放解析",
}
question = checked(teacher, "POST", "/api/v1/questions", quiz_question, status=201)[
    "id"
]
checked(
    teacher, "POST", f"/api/v1/questions/{question}/reviews", {"expected_version": 1}
)
now = datetime.now(UTC)
quiz = checked(
    teacher,
    "POST",
    "/api/v1/quizzes",
    {
        "title": "课末合成测验",
        "chapter_id": None,
        "deadline_at": (now + timedelta(hours=1)).isoformat(),
        "answers_open_at": (now + timedelta(hours=2)).isoformat(),
        "items": [{"question_id": question, "points": 10}],
    },
    status=201,
)["id"]
quiz_path = f"/api/v1/quizzes/{quiz}"
published = checked(teacher, "POST", quiz_path + "/publications", {})
item = published["items"][0]["id"]
view = checked(student, "GET", quiz_path)
assert all("answer" not in row and "explanation" not in row for row in view["items"])
checked(
    student,
    "POST",
    quiz_path + "/submissions",
    {"draft_revision": 0, "answers": {item: "A"}},
    status=201,
)
checked(student, "GET", quiz_path + "/my-submission")
grading = (quiz_submissions, quiz_results, jobs, outbox)
before = snapshot(*grading)
assert len(before[0]) == len(before[1]) == 1
score_probe = call(student, "PATCH", quiz_path + "/submission-results", {})
unchanged = before == snapshot(*grading)


class ModelEndpoint:
    def request(self, method, path, payload, deadline, **kwargs):
        assert (method, path) == ("POST", "/chat/completions")
        return {
            "model": payload["model"],
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "insufficient": False,
                                "claims": [
                                    {
                                        "text": "蓝鲸动力站的额定电压为24伏。",
                                        "evidence": [1],
                                    }
                                ],
                                "more": False,
                            }
                        )
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
        }


model_client.endpoint = ModelEndpoint()
app.extensions["private_sessions"].ai.chat = model_client
session = checked(
    student,
    "POST",
    "/api/v1/sessions",
    {"assistant_id": assist_id, "mode": "material_qa"},
    status=201,
)
run_response = call(
    student,
    "POST",
    f"/api/v1/sessions/{session['id']}/messages",
    {"question": "蓝鲸动力站的额定电压是多少？"},
)
assert run_response.status_code == 200 and run_response.mimetype == "text/event-stream"
frames = {
    part.splitlines()[0][7:]: json.loads(part.split("data: ", 1)[1])["data"]
    for part in run_response.get_data(as_text=True).split("\n\n")
    if part.startswith("event: ")
}
assert "done" in frames and "error" not in frames
run_id = frames["done"]["run_id"]
run_path = f"/api/v1/runs/{run_id}"
private_run = checked(student, "GET", run_path)
assert call(teacher, "GET", run_path).status_code == 404
with engine.connect() as connection:
    stored = connection.execute(
        select(
            runs.c.owner_id, runs.c.configuration, runs.c.status, runs.c.duration_ms
        ).where(runs.c.id == run_id)
    ).one()
assert stored.owner_id == actor("a_student").id
assert stored.configuration["skill"] == {"id": skill_id, "revision": 2}
assert stored.status == "succeeded" and stored.duration_ms >= 0

audit_path = "/api/v1/operation-audits"
assert call(student, "GET", audit_path).status_code == 403
assert call(anonymous, "GET", audit_path).status_code == 401
skill_audits = checked(teacher, "GET", audit_path + "?skill_id=" + skill_id)["items"]
execution = next(row for row in skill_audits if row["action"] == "skill_execute")
assert execution == {
    "id": execution["id"],
    "request_id": run_response.headers["X-Request-ID"],
    "actor_id": a1.id,
    "created_at": execution["created_at"],
    "action": "skill_execute",
    "resource_type": "skill",
    "resource_id": skill_id,
    "outcome": "succeeded",
    "skill_id": skill_id,
    "total_tokens": 30,
    "usage_status": "measured",
    "duration_ms": stored.duration_ms,
}
assert run_id not in json.dumps(execution) and session["id"] not in json.dumps(
    execution
)
student_audits = checked(teacher, "GET", audit_path + f"?actor_id={a1.id}&days=1")
denials = [row for row in student_audits["items"] if row["outcome"] == "denied"]
assert sorted(row["request_id"] for row in denials) == sorted(denial_requests)
assert all(
    row["resource_id"] is None and row["usage_status"] == "not_applicable"
    for row in denials
)
checked(other_teacher, "POST", "/api/v1/prompt-templates", template, status=201)
with engine.connect() as connection:
    foreign_event = connection.scalar(
        select(events.c.id).where(events.c.class_id == b.class_id).limit(1)
    )
assert foreign_event
assert call(other_teacher, "GET", audit_path + "/" + foreign_event).status_code == 200
assert envelope(call(teacher, "GET", audit_path + "/" + foreign_event)) == envelope(
    call(teacher, "GET", audit_path + "/" + str(uuid4()))
)
assert checked(teacher, "GET", audit_path + "?actor_id=" + b.id)["total"] == 0
assert call(teacher, "GET", audit_path + "?days=8").json["code"] == 1000


def fail_audit(_conn, _cursor, statement, _params, _context, _executemany):
    if statement.startswith("INSERT INTO operation_audit_events"):
        raise OperationalError(
            None, None, RuntimeError("synthetic audit storage fault")
        )


audit_engine = app.extensions["private_sessions"].repository.engine
audit_tables = (skills, skill_revisions, templates, template_revisions, audits, events)
before_fault = snapshot(*audit_tables)
event.listen(audit_engine, "before_cursor_execute", fail_audit)
try:
    route = f"/api/v1/prompt-templates/{template_id}"
    patch_template = {
        "name": "合成审计故障对照",
        "prompt": "{{input}}",
        "enabled": True,
        "revision": 2,
    }
    unavailable = envelope(call(teacher, "PATCH", route, patch_template))
    assert unavailable[:2] == (503, 1500) and unavailable[3] is None
    assert envelope(call(student, "PATCH", route, patch_template))[:2] == (403, 1200)
    assert snapshot(*audit_tables) == before_fault
finally:
    event.remove(audit_engine, "before_cursor_execute", fail_audit)

cleanup = app.extensions["private_sessions"].repository
audit_backup = [dict(row._mapping) for row in snapshot(events)[0]]
assert all("\n" not in row["event_json"] for row in audit_backup)
assert (
    next(
        json.loads(row["event_json"])
        for row in audit_backup
        if row["id"] == execution["id"]
    )
    == execution
)
future = utc_now() + timedelta(days=91)
assert cleanup.cleanup_expired(utc_now())["operation_audit_expired"] == 0
assert cleanup.cleanup_expired(future)["operation_audit_expired"] == len(audit_backup)
with engine.begin() as connection:
    connection.execute(insert(events), audit_backup)
assert cleanup.cleanup_expired(future)["operation_audit_expired"] == len(audit_backup)
assert cleanup.cleanup_expired(future)["operation_audit_expired"] == 0

prior_accounts = snapshot(accounts)
config = Config()
config.set_main_option(
    "script_location", str(Path("app/adapters/migrations").resolve())
)
with engine.connect() as connection:
    config.attributes["connection"] = connection
    command.downgrade(config, "0012_teaching_jobs")
    connection.commit()
assert not inspect(engine).has_table(events.name)
assert inspect(engine).has_table(jobs.name) and snapshot(accounts) == prior_accounts
migrate(engine)
migrate(engine)
assert inspect(engine).has_table(events.name) and snapshot(accounts) == prior_accounts

write_routes = [
    f"{method} {rule.rule}"
    for rule in app.url_map.iter_rules()
    if rule.rule.startswith("/api/v1/")
    for method in sorted(rule.methods & {"POST", "PUT", "PATCH", "DELETE"})
]
report = {
    "anonymous": anon_results,
    "search_counts": [len(a_hits), len(b_hits), len(cross_hits)],
    "cross": foreign,
    "missing": missing,
    "configuration": config_results,
    "grading": {
        "http": score_probe.status_code,
        "unchanged": unchanged,
        "before_counts": list(map(len, before)),
    },
    "skill_audit": {
        "request_id": run_response.headers.get("X-Request-ID"),
        "run_fields": sorted(private_run),
        "status": private_run.get("status"),
        "duration_ms": private_run.get("duration_ms"),
        "skill_selected": skill_id in json.dumps(private_run),
        "usage_present": "usage" in private_run,
        "actor_matches_database": stored.owner_id == actor("a_student").id,
        "operation_audit_tokens": execution["total_tokens"],
        "denial_audits": len(denials),
    },
    "write_routes": sorted(write_routes),
}
print("SECURITY_PRECHECK " + json.dumps(report, ensure_ascii=False))

frontend = Path("/tmp/campusclaw-security-frontend")
frontend.mkdir()
for filename, client, path in (
    ("login.html", anonymous, "/login"),
    ("materials.html", teacher, "/materials"),
    ("quizzes.html", student, "/quizzes"),
    ("swagger.html", teacher, "/swagger"),
    ("openapi.json", teacher, "/api/v1/openapi.json"),
):
    response = call(client, "GET", path)
    assert response.status_code == 200, (filename, response.status_code)
    (frontend / filename).write_bytes(response.data)
