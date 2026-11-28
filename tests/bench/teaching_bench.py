"""在压测专用应用容器内运行，数据库与 Kafka 均来自隔离夹具。"""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import quantiles
from time import monotonic
from unittest.mock import Mock
from uuid import UUID

from sqlalchemy import insert, select, text, update
from werkzeug.security import generate_password_hash

from app import create_app
from app.adapters.auth_repository import AuthRepository
from app.adapters.auth_schema_v1 import accounts
from app.adapters.chat_client import ChatProtocolError
from app.adapters.database import DatabaseError, mysql_engine
from app.adapters.index_clients import IndexDependencyError
from app.adapters.index_schema_v5 import builds, chunks, materials
from app.adapters.migrations.runner import migrate
from app.adapters.retrieval_repository import RetrievalRepository
from app.adapters.teaching_jobs import TeachingJobs
from app.adapters.teaching_kafka import commit, consumer, producer
from app.adapters.teaching_repository import TeachingRepository
from app.adapters.teaching_schema_v10 import question_versions, questions, quizzes
from app.api.auth import COOKIE
from app.config import Settings
from app.services.teaching_candidates import CandidateJobs
from app.teaching_worker import process_record, relay_once

ORIGIN = "https://campusclaw.test"
BOOTSTRAP = "kafka:9092"
QUOTE = "串联电路各处电流相等，并联电路各支路电压相等。"
QUERY = "/api/v1/quizzes?page_size=20"
PAGE = text(
    "SELECT * FROM quizzes WHERE class_id=:scope ORDER BY created_at DESC, id LIMIT 20"
)


def measured(concurrency, samples, action):
    def sample(number):
        started = monotonic()
        ok = action(number)
        return ok, (monotonic() - started) * 1000

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        started = monotonic()
        outcomes = list(pool.map(sample, range(samples)))
        seconds = monotonic() - started
    successful = sum(ok for ok, _ in outcomes)
    return {
        "samples": samples,
        "throughput": round(successful / seconds, 2),
        "p95_ms": round(
            quantiles([elapsed for _, elapsed in outcomes], n=20, method="inclusive")[
                -1
            ],
            2,
        ),
        "errors": samples - successful,
    }


def seed_quizzes(engine, total):
    now = datetime(2026, 1, 1)
    with engine.begin() as connection:
        for lane, name in enumerate(("demo_a_teacher", "demo_b_teacher"), 1):
            owner, cohort = connection.execute(
                select(accounts.c.id, accounts.c.class_id).where(
                    accounts.c.login_name == name
                )
            ).one()
            for start in range(0, total, 1000):
                connection.execute(
                    insert(quizzes),
                    [
                        {
                            "id": str(UUID(int=(lane << 80) + index)),
                            "class_id": cohort,
                            "chapter_id": None,
                            "creator_id": owner,
                            "title": f"压测合成班 {lane} 测验",
                            "deadline_at": now,
                            "answers_open_at": now,
                            "created_at": now + timedelta(seconds=index // 2),
                        }
                        for index in range(start, min(start + 1000, total))
                    ],
                )
        connection.execute(text("ANALYZE TABLE quizzes")).all()
        scope = connection.execute(
            select(accounts.c.class_id).where(accounts.c.login_name == "demo_a_teacher")
        ).scalar_one()
        plan = json.loads(
            connection.execute(
                text("EXPLAIN FORMAT=JSON " + PAGE.text),
                {"scope": scope},
            ).scalar_one()
        )["query_block"]
    return scope, plan


def seed_source(engine, call, teacher):
    result = call(
        teacher,
        "POST",
        "/api/v1/materials",
        {"title": "压测资料", "text": QUOTE},
        "bench-source",
    )
    assert result.status_code == 201
    source = result.json["data"]["id"]
    with engine.begin() as connection:
        row = (
            connection.execute(select(materials).where(materials.c.id == source))
            .mappings()
            .one()
        )
        pinned = {
            "class_id": row["class_id"],
            "material_id": source,
            "source_version": row["content_version"],
            "index_version": 1,
            "index_config_version": "benchmark-v1",
        }
        now = datetime.now(UTC).replace(tzinfo=None)
        connection.execute(
            insert(builds).values(
                **pinned,
                id=source,
                creator_id=row["creator_id"],
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
                id=source,
                ordinal=0,
                start_offset=0,
                end_offset=len(QUOTE),
                content=QUOTE,
            )
        )
        connection.execute(
            update(materials)
            .where(materials.c.id == source)
            .values(active_index_version=1)
        )
    return source


def main():
    levels = tuple(
        map(int, os.environ.get("CAMPUSCLAW_BENCH_LEVELS", "1,4,10").split(","))
    )
    samples = int(os.environ.get("CAMPUSCLAW_BENCH_SAMPLES", "12"))
    quiz_count = int(os.environ.get("CAMPUSCLAW_BENCH_QUIZZES", "1000"))
    if (
        not levels
        or tuple(sorted(set(levels))) != levels
        or min(levels) < 1
        or not max(2, max(levels)) <= samples <= 20
        or samples * len(levels) > 48
        or not 1000 <= quiz_count <= 30000
    ):
        raise ValueError("压测参数超出隔离样本、班级任务容量或账号限流范围")
    config = Settings.load(
        {**os.environ, "APP_PUBLIC_ORIGIN": ORIGIN, "TEACHING_JOBS_ENABLED": "1"},
        Path("app/BUILD_VERSION"),
    )
    if not config.mysql_database.startswith("campusclaw_test_"):
        raise ValueError("压测只允许使用隔离合成库")
    engine = mysql_engine(
        host=config.mysql_host,
        port=config.mysql_port,
        database=config.mysql_database,
        user=config.mysql_user,
        password=config.mysql_password,
    )
    migrate(engine)
    AuthRepository(engine).seed_demo_accounts(
        generate_password_hash(config.mysql_password, method="scrypt")
    )
    with engine.begin() as connection:
        reader = dict(
            connection.execute(
                select(accounts).where(accounts.c.login_name == "demo_a_student")
            )
            .mappings()
            .one()
        )
        reader.update(id=str(UUID(int=2)), login_name="bench_search_student")
        connection.execute(insert(accounts).values(reader))
    repository = TeachingJobs(engine)
    example = {
        "kind": "true_false",
        "stem": "串联电路各处电流相等。",
        "options": ["正确", "错误"],
        "answer": "true",
        "explanation": QUOTE,
        "evidence": 1,
        "quote": QUOTE,
    }
    model = Mock()
    model.complete_once.return_value = {"insufficient": False, "questions": [example]}
    service = CandidateJobs(
        repository,
        DatabaseError,
        RetrievalRepository(engine),
        "synthetic-model-v1",
        chat=model,
        protocol_error=ChatProtocolError,
        dependency_error=IndexDependencyError,
    )
    app = create_app(config, candidate_jobs=service)
    app.logger.disabled = True

    def call(cookie, method, path, body=None, key=None):
        headers = {"Origin": ORIGIN, "X-CampusClaw-Request": "same-origin"}
        if cookie:
            headers["Cookie"] = f"{COOKIE}={cookie}"
        if key:
            headers["Idempotency-Key"] = key
        return app.test_client(use_cookies=False).open(
            path, method=method, json=body, base_url=ORIGIN, headers=headers
        )

    def login(name):
        response = call(
            None,
            "POST",
            "/api/v1/auth/sessions",
            {"login_name": name, "password": config.mysql_password},
        )
        assert response.status_code == 200
        return response.headers["Set-Cookie"].split(";", 1)[0].split("=", 1)[1]

    teacher = login("demo_a_teacher")
    student = login("demo_a_student")
    peer = login("demo_b_teacher")
    search_reader = login("bench_search_student")
    scope, plan = seed_quizzes(engine, quiz_count)
    source = seed_source(engine, call, teacher)

    def list_page(actor, page=1):
        response = call(actor, "GET", f"{QUERY}&page={page}")
        assert response.status_code == 200 and response.json["code"] == 0
        return response.json["data"]

    indices = sorted(range(quiz_count), key=lambda index: (-(index // 2), index))
    expected = [str(UUID(int=(1 << 80) + index)) for index in indices]
    for page in (1, 2):
        data = list_page(teacher, page)
        assert data["total"] == quiz_count
        assert [row["id"] for row in data["items"]] == expected[
            (page - 1) * 20 : page * 20
        ]
    foreign = list_page(peer)
    expected_set = set(expected)
    assert foreign["total"] == quiz_count and all(
        row["id"] not in expected_set for row in foreign["items"]
    )
    assert list_page(student)["total"] == 0
    assert call(None, "GET", QUERY).status_code == 401

    def search(actor):
        return call(
            actor, "POST", "/api/v1/searches", {"query": "串联电路", "mode": "keyword"}
        )

    hidden = search(peer)
    assert hidden.status_code == 200 and hidden.json["data"]["items"] == []
    visible = search(student)
    assert visible.status_code == 200 and len(visible.json["data"]["items"]) == 1

    teaching = TeachingRepository(engine)
    with engine.begin() as connection:
        owner = (
            connection.execute(
                select(accounts).where(accounts.c.login_name == "demo_a_teacher")
            )
            .mappings()
            .one()
        )
        participant = connection.execute(
            select(accounts.c.id).where(accounts.c.login_name == "demo_a_student")
        ).scalar_one()
        now = datetime.now(UTC).replace(tzinfo=None)
        question_id = str(UUID(int=11))
        connection.execute(
            insert(questions).values(
                id=question_id,
                class_id=owner["class_id"],
                creator_id=owner["id"],
                current_version=1,
                reviewed_version=1,
                created_at=now,
                updated_at=now,
            )
        )
        fields = {
            "kind": "true_false",
            "stem": example["stem"],
            "options": example["options"],
            "answer": "true",
            "explanation": QUOTE,
            "source_material_id": None,
        }
        connection.execute(
            insert(question_versions).values(
                question_id=question_id,
                version=1,
                class_id=owner["class_id"],
                created_at=now,
                **fields,
            )
        )
        for number in range(len(levels) * samples):
            quiz = {
                "id": str(UUID(int=100 + number)),
                "class_id": owner["class_id"],
                "creator_id": owner["id"],
                "title": "压测交卷",
                "chapter_id": None,
                "deadline_at": now + timedelta(hours=1),
                "answers_open_at": now + timedelta(hours=2),
                "published_at": None,
                "created_at": now,
            }
            item = {
                **fields,
                "id": str(UUID(int=200 + number)),
                "position": 1,
                "class_id": quiz["class_id"],
                "quiz_id": quiz["id"],
                "question_id": question_id,
                "question_version": 1,
                "points": 1,
                "scoring_version": 1,
            }
            connection.execute(insert(quizzes).values(quiz))
            teaching.publish(connection, quiz, [item], [participant], owner["id"], now)

    def submit(number):
        quiz_id = UUID(int=100 + number)
        response = call(
            student,
            "POST",
            f"/api/v1/quizzes/{quiz_id}/submissions",
            {"draft_revision": 0, "answers": {str(UUID(int=200 + number)): "true"}},
            f"bench-submit-{number}",
        )
        return response.status_code == 202 and response.json["code"] == 0

    def retrieve(_):
        response = search(search_reader)
        return (
            response.status_code == 200
            and response.json["code"] == 0
            and len(response.json["data"]["items"]) == 1
        )

    def query(_):
        response = call(teacher, "GET", QUERY)
        return (
            response.status_code == 200
            and response.json["code"] == 0
            and len(response.json["data"]["items"]) == 20
        )

    def query_sql(_):
        with engine.connect() as connection:
            return len(connection.execute(PAGE, {"scope": scope}).all()) == 20

    for _ in range(8):
        assert query(0) and query_sql(0)

    def event_log(*_args, **_fields):
        pass

    tx = producer(BOOTSTRAP)
    rx = consumer(BOOTSTRAP)
    rows = []
    try:
        assert not rx.poll(timeout_ms=1500), "压测 broker 主题必须为空"
        for level_index, concurrency in enumerate(levels):
            jobs = []

            def accept(_, accepted=jobs):
                response = call(
                    teacher,
                    "POST",
                    "/api/v1/question-generation-jobs",
                    {"material_id": source, "count": 1},
                )
                if response.status_code != 202 or response.json["code"] != 0:
                    return False
                accepted.append(response.json["data"]["task_id"])
                return True

            rows.append((concurrency, "query", measured(concurrency, 120, query)))
            rows.append(
                (concurrency, "query_sql", measured(concurrency, 120, query_sql))
            )
            rows.append(
                (
                    concurrency,
                    "submission",
                    measured(
                        concurrency,
                        samples,
                        lambda number, offset=level_index * samples: submit(
                            offset + number
                        ),
                    ),
                )
            )
            rows.append(
                (
                    concurrency,
                    "keyword_search",
                    measured(concurrency, samples, retrieve),
                )
            )
            rows.append(
                (concurrency, "job_admission", measured(concurrency, samples, accept))
            )
            pending = set(jobs)
            completion_times = []
            started = monotonic()
            for _ in jobs:
                assert relay_once(repository, tx, event_log)
            while pending and monotonic() - started < 40:
                for batch in rx.poll(timeout_ms=500, max_records=1).values():
                    for record in batch:
                        identity = record.key.decode()
                        assert identity in pending
                        process_record(repository, service, record, event_log)
                        commit(rx, record)
                        pending.remove(identity)
                        completion_times.append((monotonic() - started) * 1000)
            seconds = monotonic() - started
            errors = len(pending)
            for job in jobs:
                response = call(teacher, "GET", f"/api/v1/teaching-jobs/{job}")
                assert response.status_code == 200
                if job not in pending:
                    errors += response.json["data"]["state"] != "succeeded"
            rows.append(
                (
                    concurrency,
                    "job_completion",
                    {
                        "samples": len(jobs),
                        "throughput": round((len(jobs) - errors) / seconds, 2),
                        "p95_ms": round(
                            quantiles(completion_times, n=20, method="inclusive")[-1], 2
                        )
                        if len(completion_times) >= 2
                        else None,
                        "errors": errors,
                    },
                )
            )
    finally:
        rx.close(autocommit=False)
        tx.close(timeout=5)
        engine.dispose()
    order = plan.get("ordering_operation", plan)
    table = order["table"]
    print(
        "teaching_benchmark",
        json.dumps(
            {
                "levels": levels,
                "samples": samples,
                "quizzes_per_class": quiz_count,
                "workers": 1,
                "explain": {
                    "key": table.get("key"),
                    "filesort": order.get("using_filesort", False),
                    "examined_estimate": table["rows_examined_per_scan"],
                },
                "rows": rows,
            }
        ),
    )
    assert all(item["errors"] == 0 for _, _, item in rows)


main()
