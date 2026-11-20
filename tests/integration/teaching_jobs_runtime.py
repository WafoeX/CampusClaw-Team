"""Real MySQL and Kafka, using a fixed model double and synthetic lesson material."""

import json
import os
import signal
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import quantiles
from time import monotonic
from unittest.mock import Mock
from uuid import uuid4

from sqlalchemy import event, func, insert, select, update
from sqlalchemy.exc import OperationalError
from werkzeug.security import generate_password_hash

from app import create_app
from app.adapters.auth_repository import AuthRepository
from app.adapters.auth_schema_v1 import accounts
from app.adapters.chat_client import ChatClient, ChatProtocolError
from app.adapters.database import DatabaseError, mysql_engine
from app.adapters.index_clients import IndexDependencyError
from app.adapters.index_schema_v5 import builds, chunks, materials
from app.adapters.migrations.runner import migrate
from app.adapters.operation_audit_schema_v13 import events
from app.adapters.retrieval_repository import RetrievalRepository
from app.adapters.teaching_jobs import TeachingJobs
from app.adapters.teaching_kafka import commit, consumer, producer, publish
from app.adapters.teaching_schema_v10 import quiz_results, quizzes
from app.adapters.teaching_schema_v12 import (
    generated_questions,
    job_results,
    jobs,
    outbox,
    quarantine,
)
from app.config import Settings
from app.services.teaching_candidates import CandidateJobs, UsageCapture
from app.teaching_job_contract import (
    CLASS_CAPACITY,
    DEAD_TOPIC,
    RETRY_SECONDS,
    TASK_TOPIC,
    Event,
)
from app.teaching_worker import process_record, relay_once

BOOTSTRAP = "kafka:9092"
ORIGIN = "https://campusclaw.test"
HEADERS = {"Origin": ORIGIN, "X-CampusClaw-Request": "same-origin"}
GENERATION = "/api/v1/question-generation-jobs"
JOB = "/api/v1/teaching-jobs/"
settings = Settings.load(
    {**os.environ, "APP_PUBLIC_ORIGIN": ORIGIN, "TEACHING_JOBS_ENABLED": "1"},
    Path("app/BUILD_VERSION"),
)
engine = mysql_engine(
    host=settings.mysql_host,
    port=settings.mysql_port,
    database=settings.mysql_database,
    user=settings.mysql_user,
    password=settings.mysql_password,
)
migrate(engine)
migrate(engine)
AuthRepository(engine).seed_demo_accounts(
    generate_password_hash(settings.mysql_password, method="scrypt")
)
repository = TeachingJobs(engine)
quote = "串联电路各处电流相等，并联电路各支路电压相等。"
sample = {
    "kind": "true_false",
    "stem": "串联电路各处电流相等。",
    "options": ["正确", "错误"],
    "answer": "true",
    "explanation": "资料说明串联电路各处电流相等。",
    "evidence": 1,
    "quote": quote,
}
model = Mock()
model.complete_once.return_value = {"insufficient": False, "questions": [sample]}
service = CandidateJobs(
    repository,
    DatabaseError,
    RetrievalRepository(engine),
    "synthetic-model-v1",
    chat=model,
    protocol_error=ChatProtocolError,
    dependency_error=IndexDependencyError,
)
app = create_app(settings, candidate_jobs=service)


def request(client, method, path, payload=None, key=None):
    headers = HEADERS | ({"Idempotency-Key": key} if key else {})
    return client.open(
        path, method=method, json=payload, headers=headers, base_url=ORIGIN
    )


def login(name):
    client = app.test_client()
    result = request(
        client,
        "POST",
        "/api/v1/auth/sessions",
        {"login_name": name, "password": settings.mysql_password},
    )
    assert result.status_code == 200, result.json
    return client, result.status_code


def view(job_id, client=None):
    response = request(client or teacher, "GET", JOB + job_id)
    assert response.status_code == 200, response.json
    return response.json["data"]


def terminal_events(job_id):
    with engine.connect() as connection:
        return (
            connection.execute(
                select(events)
                .where(
                    events.c.resource_id == job_id,
                    events.c.action == "candidate_terminal",
                )
                .order_by(events.c.created_at, events.c.id)
            )
            .mappings()
            .all()
        )


def job_usage(job_id):
    with engine.connect() as connection:
        return connection.execute(
            select(jobs.c.usage_status, jobs.c.total_tokens).where(jobs.c.id == job_id)
        ).one()


def material(client, key):
    response = request(
        client,
        "POST",
        "/api/v1/materials",
        {"title": "电路合成资料", "text": quote},
        key=key,
    )
    assert response.status_code == 201, response.json
    return response.json["data"]["id"]


def indexed(material_id, version):
    with engine.begin() as connection:
        scope = (
            connection.execute(select(materials).where(materials.c.id == material_id))
            .mappings()
            .one()
        )
        pinned = {
            "class_id": scope["class_id"],
            "material_id": material_id,
            "source_version": scope["content_version"],
            "index_version": version,
            "index_config_version": "synthetic-v1",
        }
        now = repository.now(connection)
        connection.execute(
            insert(builds).values(
                **pinned,
                id=str(uuid4()),
                creator_id=scope["creator_id"],
                mode="auto",
                window_size=600,
                overlap=100,
                status="published",
                stage="published",
                created_at=now,
                updated_at=now,
            )
        )
        connection.execute(
            insert(chunks).values(
                **pinned,
                id=str(uuid4()),
                ordinal=0,
                start_offset=0,
                end_offset=len(quote),
                content=quote,
            )
        )
        connection.execute(
            update(materials)
            .where(materials.c.id == material_id)
            .values(active_index_version=version)
        )


def task(material_id, count=1):
    start = monotonic()
    response = request(
        teacher, "POST", GENERATION, {"material_id": material_id, "count": count}
    )
    elapsed = (monotonic() - start) * 1000
    assert response.status_code == 202, response.json
    job_id = response.json["data"]["task_id"]
    assert response.headers["Location"] == JOB + job_id
    assert view(job_id)["state"] == "pending"
    with engine.connect() as connection:
        audit = (
            connection.execute(
                select(events).where(
                    events.c.resource_type == "teaching_job",
                    events.c.resource_id == job_id,
                    events.c.action == "candidate_admit",
                )
            )
            .mappings()
            .one()
        )
        job = repository.job(connection, job_id)
    assert audit["request_id"] == response.json["request_id"]
    assert audit["class_id"] == job["class_id"]
    assert audit["actor_id"] == job["creator_id"]
    assert audit["outcome"] == "succeeded" and audit["skill_id"] is None
    assert audit["usage_status"] == "not_applicable" and audit["total_tokens"] is None
    assert audit["duration_ms"] >= 0
    assert all(word not in audit["event_json"] for word in (quote, "answer", "prompt"))
    return job_id, elapsed, start


def job_event(job_id):
    with engine.connect() as connection:
        row = repository.job(connection, job_id)
        return Event(row["event_id"], row["id"], row["generation"], row["trace_id"])


def outbox_row(event_id):
    with engine.connect() as connection:
        return (
            connection.execute(select(outbox).where(outbox.c.id == event_id))
            .mappings()
            .one()
        )


def due(event_id, *, topic=None, abandon=False):
    with engine.begin() as connection:
        now = repository.now(connection)
        changes = {"available_at": now - timedelta(seconds=1)}
        if topic:
            changes["topic"] = topic
        if abandon:
            changes["lease_until"] = now - timedelta(seconds=1)
        connection.execute(
            update(outbox).where(outbox.c.id == event_id).values(**changes)
        )
        connection.execute(
            update(jobs).where(jobs.c.event_id == event_id).values(available_at=now)
        )


def find_record(transport, match, *, process_others=True, on_other=None):
    deadline = monotonic() + 50
    while monotonic() < deadline:
        for records in transport.poll(timeout_ms=500, max_records=1).values():
            for record in records:
                if match(record):
                    return record
                if on_other:
                    on_other(record)
                if process_others:
                    process_record(repository, service, record, event_log)
                    commit(transport, record)
    raise AssertionError("broker did not deliver the expected record")


def consume_event(transport, expected):
    record = find_record(
        transport,
        lambda rec: (
            rec.key == expected.task_id.encode()
            and json.loads(rec.value)["event_id"] == expected.event_id
        ),
    )
    process_record(repository, service, record, event_log)
    commit(transport, record)
    return record


def event_log(name, **fields):
    observed.append((name, fields))


teacher, teacher_login_status = login("demo_a_teacher")
student, _ = login("demo_a_student")
outsider, outsider_login_status = login("demo_b_teacher")
source = material(teacher, "candidate-source")
empty = material(teacher, "candidate-empty")
foreign = material(outsider, "candidate-foreign")
indexed(source, 1)
missing = str(uuid4())
assert (
    request(
        student, "POST", GENERATION, {"material_id": source, "count": 1}
    ).status_code
    == 403
)
assert (
    request(
        teacher, "POST", GENERATION, {"material_id": source, "count": 11}
    ).status_code
    == 400
)
for target in (foreign, missing):
    response = request(teacher, "POST", GENERATION, {"material_id": target, "count": 1})
    assert response.status_code == 404 and response.json["code"] == 1300


# A failing outbox insert rolls back both admission writes.
def reject_outbox(_conn, _cursor, statement, *_):
    if statement.startswith("INSERT INTO teaching_outbox"):
        raise OperationalError("injected outbox write failure", None, RuntimeError())


event.listen(engine, "before_cursor_execute", reject_outbox)
try:
    denied = request(teacher, "POST", GENERATION, {"material_id": source, "count": 1})
    assert denied.status_code == 503 and denied.json["code"] == 1500
finally:
    event.remove(engine, "before_cursor_execute", reject_outbox)
with engine.connect() as connection:
    assert connection.scalar(select(func.count()).select_from(jobs)) == 0
    assert connection.scalar(select(func.count()).select_from(events)) == 0


def reject_audit(_conn, _cursor, statement, *_):
    if statement.startswith("INSERT INTO operation_audit_events"):
        raise OperationalError("injected audit write failure", None, RuntimeError())


event.listen(engine, "before_cursor_execute", reject_audit)
try:
    denied = request(teacher, "POST", GENERATION, {"material_id": source, "count": 1})
    assert denied.status_code == 503 and denied.json["code"] == 1500
finally:
    event.remove(engine, "before_cursor_execute", reject_audit)
with engine.connect() as connection:
    assert connection.scalar(select(func.count()).select_from(jobs)) == 0
    assert connection.scalar(select(func.count()).select_from(outbox)) == 0
    assert connection.scalar(select(func.count()).select_from(events)) == 0

observed = []

if sys.argv[1:] == ["storage"]:
    job_id, _, _ = task(source)
    expected = job_event(job_id)
    publication = repository.claim_outbox()
    assert publication["payload"] == expected.payload()
    assert publication["message_key"] == job_id and publication["sent_at"] is None
    repository.delivery_receipt(publication, delivered=False)
    assert outbox_row(expected.event_id)["sent_at"] is None
    due(expected.event_id)
    publication = repository.claim_outbox()
    repository.delivery_receipt(publication, delivered=True)
    assert outbox_row(expected.event_id)["sent_at"] is not None
    claim = repository.claim_job(expected)
    drafts = service.generate(claim)

    def reject_result(_conn, _cursor, statement, *_):
        if statement.startswith("INSERT INTO teaching_job_results"):
            raise OperationalError(
                "injected result write failure", None, RuntimeError()
            )

    event.listen(engine, "before_cursor_execute", reject_result)
    try:
        try:
            service.complete(claim, drafts=drafts)
        except OperationalError:
            pass
        else:
            raise AssertionError("result failure must roll back candidate drafts")
    finally:
        event.remove(engine, "before_cursor_execute", reject_result)
    with engine.connect() as connection:
        assert (
            connection.scalar(select(func.count()).select_from(generated_questions))
            == 0
        )
        assert connection.scalar(select(func.count()).select_from(job_results)) == 0
        assert (
            connection.scalar(
                select(func.count())
                .select_from(events)
                .where(
                    events.c.resource_id == job_id,
                    events.c.action == "candidate_terminal",
                )
            )
            == 0
        )

    event.listen(engine, "before_cursor_execute", reject_audit)
    try:
        try:
            service.complete(claim, drafts=drafts)
        except OperationalError:
            pass
        else:
            raise AssertionError(
                "terminal audit failure must roll back drafts and state"
            )
    finally:
        event.remove(engine, "before_cursor_execute", reject_audit)
    assert view(job_id)["state"] == "running"
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(job_results)) == 0
        assert (
            connection.scalar(select(func.count()).select_from(generated_questions))
            == 0
        )
    with engine.begin() as connection:
        now = repository.now(connection)
        connection.execute(
            update(jobs)
            .where(jobs.c.id == job_id)
            .values(lease_until=now - timedelta(seconds=1))
        )
    assert repository.recover() == 1
    recovered = repository.claim_job(expected)
    assert recovered["lease_id"] != claim["lease_id"]
    assert not service.complete(claim, drafts=drafts)
    measured = UsageCapture()
    measured.note_call()
    measured.record_model_usage(17)
    assert service.complete(recovered, drafts=drafts, usage=measured, duration_ms=9)
    assert view(job_id)["state"] == "succeeded"
    with engine.connect() as connection:
        terminal = (
            connection.execute(
                select(events).where(
                    events.c.resource_id == job_id,
                    events.c.action == "candidate_terminal",
                )
            )
            .mappings()
            .one()
        )
    assert terminal["outcome"] == "succeeded"
    assert terminal["usage_status"] == "measured"
    assert terminal["total_tokens"] == 17 and terminal["duration_ms"] == 9
    assert terminal["skill_id"] is None
    with engine.connect() as connection:
        settled = repository.job(connection, job_id)
    assert settled["usage_status"] == "measured" and settled["total_tokens"] == 17
    assert repository.claim_job(expected) is None
    question_id = view(job_id)["result"]["question_ids"][0]
    deadline = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
    quiz_payload = {
        "title": "候选题出处回归",
        "chapter_id": None,
        "deadline_at": deadline,
        "answers_open_at": deadline,
        "items": [{"question_id": question_id, "points": 10}],
    }
    quiz = request(teacher, "POST", "/api/v1/quizzes", quiz_payload)
    assert quiz.status_code == 201
    quiz_id = quiz.json["data"]["id"]
    path = "/api/v1/quizzes/" + quiz_id
    assert request(teacher, "POST", path + "/publications", {}).status_code == 409
    assert (
        request(
            teacher,
            "POST",
            f"/api/v1/questions/{question_id}/reviews",
            {"expected_version": 1},
        ).status_code
        == 200
    )
    published = request(teacher, "POST", path + "/publications", {})
    assert published.status_code == 200
    item_id = published.json["data"]["items"][0]["id"]
    assert (
        request(
            student,
            "POST",
            path + "/submissions",
            {"draft_revision": 0, "answers": {item_id: "false"}},
            key="wrong-candidate",
        ).status_code
        == 201
    )
    with engine.begin() as connection:
        now = repository.now(connection)
        connection.execute(
            update(quizzes)
            .where(quizzes.c.id == quiz_id)
            .values(answers_open_at=now - timedelta(seconds=1))
        )
    prior = request(student, "GET", path + "/my-mistakes").json["data"]["items"][0]
    assert (
        prior["source_snapshot"]["text"] == quote
        and prior["source_snapshot"]["index_version"] == 1
    )
    indexed(source, 2)
    rebuilt = request(student, "GET", path + "/my-mistakes").json["data"]["items"][0]
    assert rebuilt["source_snapshot"] == prior["source_snapshot"]
    assert request(teacher, "DELETE", "/api/v1/materials/" + source).status_code == 200
    detail = request(teacher, "GET", "/api/v1/questions/" + question_id).json["data"]
    assert detail["source_material_id"] is None and "source_snapshot" not in detail
    redacted = request(student, "GET", path + "/my-mistakes").json["data"]["items"][0]
    assert (
        redacted["source_snapshot"] is None
        and redacted["source_status"] == "unavailable"
    )
    assert request(student, "GET", path + "/my-submission").json["data"]["score"] == 0
    print("teaching_job_storage_ok")
    sys.exit(0)

tx = producer(BOOTSTRAP)
job_id, acceptance, started = task(source)
expected = job_event(job_id)
assert view(job_id, teacher)["result"] is None
assert request(outsider, "GET", JOB + job_id).json["code"] == 1300
assert request(outsider, "POST", JOB + job_id + "/replays", {}).json["code"] == 1300
assert request(student, "GET", JOB + job_id).json["code"] == 1200
assert model.complete_once.call_count == 0

# Missing destination and lost receipt both leave the event pending with its original ID.
due(expected.event_id, topic="campusclaw.teaching.missing.test")
assert not relay_once(repository, tx, event_log)
assert (
    outbox_row(expected.event_id)["sent_at"] is None and job_event(job_id) == expected
)
due(expected.event_id, topic=TASK_TOPIC)
abandoned = repository.claim_outbox()
assert publish(tx, abandoned)
assert outbox_row(expected.event_id)["sent_at"] is None
due(expected.event_id, abandon=True)
assert relay_once(repository, tx, event_log)
assert outbox_row(expected.event_id)["sent_at"] is not None
assert view(job_id)["state"] == "pending"

# Exit the consumer process after DB commit and before committing the Kafka position.
tx.close(timeout=5)
engine.dispose()
pid = os.fork()
if pid == 0:
    try:
        rx = consumer(BOOTSTRAP)
        record = find_record(rx, lambda rec: rec.key == job_id.encode())
        process_record(repository, service, record, event_log)
        os.kill(os.getpid(), signal.SIGKILL)
    except Exception:
        import traceback

        traceback.print_exc()
        os._exit(1)
_, status = os.waitpid(pid, 0)
assert os.WIFSIGNALED(status) and os.WTERMSIG(status) == signal.SIGKILL
tx = producer(BOOTSTRAP)
first = view(job_id)
assert first["state"] == "succeeded", first
completion = (monotonic() - started) * 1000
question_id = first["result"]["question_ids"][0]

rx = consumer(BOOTSTRAP)
first_record = consume_event(rx, expected)
duplicate = consume_event(rx, expected)
assert duplicate.offset > first_record.offset
assert view(job_id) == first
with engine.connect() as connection:
    assert connection.scalar(select(func.count()).select_from(generated_questions)) == 1
    assert connection.scalar(select(func.count()).select_from(job_results)) == 1
question = request(teacher, "GET", "/api/v1/questions/" + question_id).json["data"]
assert question["origin"] == "ai" and question["reviewed"] is False
assert question["source_snapshot"]["text"] == quote
assert model.complete_once.call_count == 0
assert request(teacher, "POST", JOB + job_id + "/replays", {}).status_code == 409

# SR-N03：已登录教师提交任务，并用同一会话逐次查询实际状态。
accepted = request(teacher, "POST", GENERATION, {"material_id": source, "count": 1})
assert accepted.status_code == 202, accepted.json
clean_job = accepted.json["data"]["task_id"]
assert accepted.headers["Location"] == JOB + clean_job
pending = view(clean_job)["state"]
assert pending == "pending"
clean_event = job_event(clean_job)
assert outbox_row(clean_event.event_id)["sent_at"] is None
assert relay_once(repository, tx, event_log)
clean_record = find_record(
    rx, lambda record: record.key == clean_job.encode(), process_others=False
)
assert json.loads(clean_record.value)["event_id"] == clean_event.event_id
claim = repository.claim_job(clean_event)
running = view(clean_job)["state"]
assert running == "running"
assert service.complete(claim, drafts=service.generate(claim))
commit(rx, clean_record)
succeeded = view(clean_job)["state"]
assert succeeded == "succeeded"

# B 班教师能读取本班讲义，访问 A 班讲义与访问缺失讲义的响应同构。
materials_url = "/api/v1/materials/"
own_material = request(outsider, "GET", materials_url + foreign)
assert own_material.status_code == 200 and own_material.json["data"]["id"] == foreign
cross_class = request(outsider, "GET", materials_url + source)
absent_material = request(outsider, "GET", materials_url + missing)
assert cross_class.status_code == absent_material.status_code == 404
assert cross_class.json["code"] == 1300
assert {
    key: value for key, value in cross_class.json.items() if key != "request_id"
} == {key: value for key, value in absent_material.json.items() if key != "request_id"}

with engine.connect() as connection:
    assert (
        connection.scalar(
            select(func.count()).select_from(outbox).where(outbox.c.job_id == clean_job)
        )
        == 1
    )
    assert (
        connection.scalar(
            select(func.count())
            .select_from(job_results)
            .where(job_results.c.job_id == clean_job)
        )
        == 1
    )
    assert (
        connection.scalar(
            select(func.count())
            .select_from(jobs.outerjoin(outbox, jobs.c.event_id == outbox.c.id))
            .where(outbox.c.id.is_(None))
        )
        == 0
    )
assert not relay_once(repository, tx, event_log)
deliveries = [
    record
    for name, record in observed
    if name == "teaching_delivery" and record["event_id"] == clean_event.event_id
]
assert deliveries == [
    {"task_id": clean_job, "event_id": clean_event.event_id, "delivered": True}
]
print(
    "security_normal_delivery",
    json.dumps(
        {
            "login_http": teacher_login_status,
            "http": accepted.status_code,
            "task_id": clean_job,
            "states": [pending, running, succeeded],
            "other_class_login_http": outsider_login_status,
            "own_material_http": own_material.status_code,
            "cross_class_material_http": cross_class.status_code,
            "cross_class_material_code": cross_class.json["code"],
            "missing_material_http": absent_material.status_code,
            "deliveries": len(deliveries),
            "outbox": 1,
            "results": 1,
            "orphan_jobs": 0,
        }
    ),
)

# Expired jobs may be claimed again. The old executor cannot publish.
stale_job, _, _ = task(source)
stale_event = job_event(stale_job)
old = repository.claim_job(stale_event)
drafts = service.generate(old)
with engine.begin() as connection:
    now = repository.now(connection)
    connection.execute(
        update(jobs)
        .where(jobs.c.id == stale_job)
        .values(lease_until=now - timedelta(seconds=1))
    )
assert repository.recover() == 1
new = repository.claim_job(stale_event)
assert old["lease_id"] != new["lease_id"]
service.complete(old, drafts=drafts)
assert view(stale_job)["state"] == "running"
assert terminal_events(stale_job) == []
service.complete(new, drafts=drafts)
assert view(stale_job)["state"] == "succeeded"
assert len(terminal_events(stale_job)) == 1
assert relay_once(repository, tx, event_log)
consume_event(rx, stale_event)
assert len(terminal_events(stale_job)) == 1

# Acknowledged records beyond the recovery window are republished using the same event ID.
recover_job, _, _ = task(source)
recover_event = job_event(recover_job)
with engine.begin() as connection:
    now = repository.now(connection)
    connection.execute(
        update(outbox)
        .where(outbox.c.id == recover_event.event_id)
        .values(sent_at=now - timedelta(minutes=10))
    )
assert repository.recover() == 1
assert job_event(recover_job) == recover_event
assert outbox_row(recover_event.event_id)["sent_at"] is None
assert relay_once(repository, tx, event_log)
consume_event(rx, recover_event)
assert view(recover_job)["state"] == "succeeded"

# Invalid Kafka records are quarantined once and skipped only after durable isolation.
bad_key = b"synthetic-invalid-record"
tx.send(TASK_TOPIC, key=bad_key, value=b"broken-json").get(timeout=15)
record = find_record(rx, lambda rec: rec.key == bad_key)
for _ in range(2):
    process_record(repository, service, record, event_log)
commit(rx, record)
with engine.connect() as connection:
    assert connection.scalar(select(func.count()).select_from(quarantine)) == 1
assert relay_once(repository, tx, event_log)

# Empty evidence, refusal, fabricated quote, bad numbers, and a valid batch.
admission_samples = [acceptance]
completion_samples = [completion]
for output, expected_reason in (
    (None, "no_evidence"),
    ({"insufficient": True, "questions": []}, "insufficient_evidence"),
    (
        {
            "insufficient": False,
            "questions": [sample, {**sample, "stem": "不同题", "quote": "虚构引用"}],
        },
        None,
    ),
    (
        {
            "insufficient": False,
            "questions": [{**sample, "explanation": "电流为 95 安。"}],
        },
        None,
    ),
    (
        {
            "insufficient": False,
            "questions": [
                sample,
                {
                    **sample,
                    "stem": "并联电路各支路电压相等。",
                    "explanation": "资料说明并联电路各支路电压相等。",
                },
            ],
        },
        "success",
    ),
):
    before = model.complete_once.call_count
    model.complete_once.return_value = output
    current, elapsed, start = task(
        empty if output is None else source,
        2 if output and len(output["questions"]) == 2 else 1,
    )
    assert relay_once(repository, tx, event_log)
    consume_event(rx, job_event(current))
    result = view(current)
    if expected_reason == "success":
        assert (
            result["state"] == "succeeded"
            and len(result["result"]["question_ids"]) == 2
        )
        admission_samples.append(elapsed)
        completion_samples.append((monotonic() - start) * 1000)
    else:
        assert result["state"] == "failed" and result["result"] is None
        assert (
            result["error_code"] == 1501 and result["error_reason"] == expected_reason
        )
    assert model.complete_once.call_count == before + (output is not None)

# Bounded transient retries end in a durable dead letter. An authorized replay can succeed once.
model.complete_once.side_effect = IndexDependencyError("synthetic", transient=True)
failed_job, _, _ = task(source)
for attempt in range(len(RETRY_SECONDS) + 1):
    current = job_event(failed_job)
    assert relay_once(repository, tx, event_log)
    consume_event(rx, current)
    state = view(failed_job)
    assert state["attempt"] == min(attempt + 1, len(RETRY_SECONDS))
    if attempt < len(RETRY_SECONDS):
        assert state["state"] == "retry_wait" and state["retry_at"] is not None
        assert not relay_once(repository, tx, event_log)
        due(job_event(failed_job).event_id)
assert state["state"] == "dead_letter" and state["error_code"] == 1500
assert state["result"] is None
assert job_usage(failed_job) == ("unavailable", None)
failed_events = terminal_events(failed_job)
assert len(failed_events) == 1
assert failed_events[0]["outcome"] == "dead_letter"
assert failed_events[0]["usage_status"] == "unavailable"
assert failed_events[0]["total_tokens"] is None

# QB-F04: the model remains unavailable while a teacher creates and publishes
# a manual question and a student receives a committed deterministic score.
calls_after_failure = model.complete_once.call_count
manual_fields = ("kind", "stem", "options", "answer", "explanation")
manual = request(
    teacher, "POST", "/api/v1/questions", {key: sample[key] for key in manual_fields}
)
assert manual.status_code == 201 and manual.json["code"] == 0
manual_id = manual.json["data"]["id"]
assert (
    request(
        teacher,
        "POST",
        f"/api/v1/questions/{manual_id}/reviews",
        {"expected_version": 1},
    ).status_code
    == 200
)
deadline = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
manual_quiz = request(
    teacher,
    "POST",
    "/api/v1/quizzes",
    {
        "title": "模型停机时的人工测验",
        "chapter_id": None,
        "deadline_at": deadline,
        "answers_open_at": deadline,
        "items": [{"question_id": manual_id, "points": 10}],
    },
)
assert manual_quiz.status_code == 201
manual_path = "/api/v1/quizzes/" + manual_quiz.json["data"]["id"]
published = request(teacher, "POST", manual_path + "/publications", {})
assert published.status_code == 200
item = published.json["data"]["items"][0]["id"]
submitted = request(
    student,
    "POST",
    manual_path + "/submissions",
    {"draft_revision": 0, "answers": {item: "true"}},
    key="manual-during-model-outage",
)
assert submitted.status_code == 201 and submitted.json["code"] == 0
with engine.connect() as connection:
    assert (
        connection.scalar(
            select(quiz_results.c.score).where(
                quiz_results.c.submission_id == submitted.json["data"]["submission_id"]
            )
        )
        == 10
    )
assert model.complete_once.call_count == calls_after_failure

with engine.connect() as connection:
    dead = (
        connection.execute(
            select(outbox).where(
                outbox.c.job_id == failed_job, outbox.c.topic == DEAD_TOPIC
            )
        )
        .mappings()
        .one()
    )
due(dead["id"], topic="campusclaw.teaching.missing.test")
assert not relay_once(repository, tx, event_log)
assert outbox_row(dead["id"])["sent_at"] is None
due(dead["id"], topic=DEAD_TOPIC)
assert relay_once(repository, tx, event_log)
model.complete_once.side_effect = None
model.complete_once.return_value = {"insufficient": False, "questions": [sample]}
with engine.connect() as connection:
    outbox_before_replay = connection.scalar(select(func.count()).select_from(outbox))
event.listen(engine, "before_cursor_execute", reject_audit)
try:
    rejected_replay = request(teacher, "POST", JOB + failed_job + "/replays", {})
    assert rejected_replay.status_code == 503 and rejected_replay.json["code"] == 1500
finally:
    event.remove(engine, "before_cursor_execute", reject_audit)
assert view(failed_job)["generation"] == 1
with engine.connect() as connection:
    assert (
        connection.scalar(select(func.count()).select_from(outbox))
        == outbox_before_replay
    )
    assert (
        connection.scalar(
            select(func.count())
            .select_from(events)
            .where(
                events.c.resource_id == failed_job,
                events.c.action == "candidate_replay",
            )
        )
        == 0
    )
replay_response = request(teacher, "POST", JOB + failed_job + "/replays", {})
assert replay_response.status_code == 202
assert view(failed_job)["generation"] == 2
assert job_usage(failed_job) == (None, None)
with engine.connect() as connection:
    replay_audit = (
        connection.execute(
            select(events).where(
                events.c.resource_id == failed_job,
                events.c.action == "candidate_replay",
            )
        )
        .mappings()
        .one()
    )
assert replay_audit["request_id"] == replay_response.json["request_id"]
assert replay_audit["skill_id"] is None
assert relay_once(repository, tx, event_log)
consume_event(rx, job_event(failed_job))
assert view(failed_job)["state"] == "succeeded"
assert [row["outcome"] for row in terminal_events(failed_job)] == [
    "dead_letter",
    "succeeded",
]

# Optional explicit real-gateway evidence, on the same isolated dependencies.
if settings.chat is not None and settings.chat.api_key:
    prior_chat, prior_version = service.chat, service.model_version
    model_observations = []
    service.chat, service.model_version = (
        ChatClient(
            settings.chat, on_result=lambda **fields: model_observations.append(fields)
        ),
        settings.chat.version,
    )
    try:
        real_job, real_acceptance, real_start = task(source)
        assert relay_once(repository, tx, event_log)
        consume_event(rx, job_event(real_job))
        real_result = view(real_job)
        assert real_result["state"] == "succeeded", real_result["error_code"]
        assert len(real_result["result"]["question_ids"]) == 1
        real_question_id = real_result["result"]["question_ids"][0]
        response = request(teacher, "GET", f"/api/v1/questions/{real_question_id}")
        assert response.status_code == 200
        draft = response.json["data"]
        assert draft["origin"] == "ai" and draft["reviewed"] is False
        snapshot = draft["source_snapshot"]
        assert snapshot["material_id"] == source and snapshot["index_version"] == 1
        assert snapshot["text"] == quote[snapshot["start"] : snapshot["end"]]
        assert len(model_observations) == 1
        print(
            "teaching_real_gateway_evidence",
            json.dumps(
                {
                    "acceptance_ms": round(real_acceptance, 2),
                    "completion_ms": round((monotonic() - real_start) * 1000, 2),
                    "samples": 1,
                    "gateway": model_observations[0],
                }
            ),
        )
    finally:
        service.chat, service.model_version = prior_chat, prior_version

# Rebuild preserves the old citation for authorized readers. In-flight old source fails closed.
inflight, _, _ = task(source)
current = job_event(inflight)
claim = repository.claim_job(current)
drafts = service.generate(claim)
indexed(source, 2)
service.complete(claim, drafts=drafts)
assert view(inflight)["state"] == "cancelled"
assert [row["outcome"] for row in terminal_events(inflight)] == ["cancelled"]
after_rebuild = request(teacher, "GET", "/api/v1/questions/" + question_id).json["data"]
assert after_rebuild["source_snapshot"] == question["source_snapshot"]
assert relay_once(repository, tx, event_log)
consume_event(rx, current)

# In-flight role changes and removal prevent publication even after a valid model response.
revoked, _, _ = task(source)
current = job_event(revoked)
claim = repository.claim_job(current)
drafts = service.generate(claim)
with engine.begin() as connection:
    connection.execute(
        update(accounts)
        .where(accounts.c.id == claim["creator_id"])
        .values(role="student")
    )
service.complete(claim, drafts=drafts)
assert request(teacher, "GET", JOB + revoked).status_code == 403
with engine.begin() as connection:
    connection.execute(
        update(accounts)
        .where(accounts.c.id == claim["creator_id"])
        .values(role="teacher")
    )
assert view(revoked)["state"] == "cancelled"
assert [row["outcome"] for row in terminal_events(revoked)] == ["cancelled"]
assert relay_once(repository, tx, event_log)
consume_event(rx, current)

deleted, _, _ = task(source)
current = job_event(deleted)
claim = repository.claim_job(current)
drafts = service.generate(claim)
assert request(teacher, "DELETE", "/api/v1/materials/" + source).status_code == 200
service.complete(claim, drafts=drafts)
assert view(deleted)["state"] == "cancelled"
assert [row["outcome"] for row in terminal_events(deleted)] == ["cancelled"]
after_delete = request(teacher, "GET", "/api/v1/questions/" + question_id).json["data"]
assert (
    after_delete["source_material_id"] is None and "source_snapshot" not in after_delete
)

# Saturation applies to new asynchronous requests. Previously accepted rows are still pending.
for index in range(CLASS_CAPACITY):
    _, elapsed, _ = task(empty, count=10 if index == 0 else 1)
    admission_samples.append(elapsed)
assert (
    request(teacher, "POST", GENERATION, {"material_id": empty, "count": 1}).status_code
    == 429
)
assert repository.metrics()["states"]["pending"] == CLASS_CAPACITY
assert repository.metrics()["oldest_pending_seconds"] >= 0
rx.close(autocommit=False)
tx.close(timeout=5)
engine.dispose()

print(
    "teaching_job_evidence",
    json.dumps(
        {
            "acceptance_samples": len(admission_samples),
            "acceptance_p95_ms": round(
                quantiles(admission_samples, n=20, method="inclusive")[-1], 2
            ),
            "completion_samples": len(completion_samples),
            "completion_ms": [round(value, 2) for value in completion_samples],
            "completion_p95_ms": round(
                quantiles(completion_samples, n=20, method="inclusive")[-1], 2
            ),
            "kafka_replays_after_crash": 2,
            "first_job_committed_batches": 1,
            "model": "fixed substitute",
        }
    ),
)
