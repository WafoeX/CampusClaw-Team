"""固定34题、真实存储及确定性模型替身；FIXTURE由可信仓库JSON注入。"""

import json
import math
import os
import re
import statistics
import time
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from sqlalchemy import insert
from werkzeug.security import check_password_hash, generate_password_hash

from app import create_app
from app.adapters.auth_repository import AuthRepository
from app.adapters.auth_schema_v1 import accounts, classes
from app.adapters.chat_client import ChatProtocolError
from app.adapters.database import DatabaseError, mysql_engine
from app.adapters.index_clients import IndexDependencyError, QdrantIndexClient
from app.adapters.index_repository import IndexRepository
from app.adapters.retrieval_repository import RetrievalRepository
from app.config import EmbeddingSettings, Settings
from app.services.answers import AnswerService
from app.services.auth import AuthService, utc_now
from app.services.indexing import IndexService
from app.services.retrieval import RetrievalService

engine = mysql_engine(
    host=os.environ["MYSQL_HOST"],
    port=int(os.environ["MYSQL_PORT"]),
    database=os.environ["MYSQL_DATABASE"],
    user=os.environ["MYSQL_USER"],
    password=os.environ["MYSQL_PASSWORD"],
)
assert engine.url.database.startswith("campusclaw_test_")
fixture = json.loads(Path("/tmp/campusclaw-retrieval-evaluation.json").read_text())
origin = "https://campusclaw.test"
config = EmbeddingSettings(
    "https://ai-gateway.devops.hello1023.com/v1", "", "course-embedding", 2048
)
settings = replace(
    Settings.load(os.environ, Path("app/BUILD_VERSION")),
    public_origin=origin,
    embedding=config,
    retrieval_min_score=0.449357,
)
headers = {"Origin": origin, "X-CampusClaw-Request": "same-origin"}
class_id = str(uuid4())
now = utc_now()
password_hash = generate_password_hash(os.environ["MYSQL_PASSWORD"], method="scrypt")
with engine.begin() as connection:
    connection.execute(
        insert(classes).values(
            id=class_id, code="evaluation", name="确定性效果回归合成班", created_at=now
        )
    )
    for role, names in [
        ("teacher", ["eval_teacher_0", "eval_teacher_1"]),
        ("student", [f"eval_student_{i}" for i in range(4)]),
    ]:
        for name in names:
            connection.execute(
                insert(accounts).values(
                    id=str(uuid4()),
                    login_name=name,
                    class_id=class_id,
                    role=role,
                    enabled=True,
                    password_hash=password_hash,
                    created_at=now,
                    updated_at=now,
                )
            )
auth = AuthService(
    AuthRepository(engine), check_password_hash, password_hash, DatabaseError
)


def topics(text):
    ids = {int(value) for value in re.findall(r"T(\d{2})", text)}
    if ids:
        return ids
    for phrase, index in [("CPU", 4), ("U=IR", 3), ("惯性", 2), ("力", 1)]:
        if phrase in text:
            return {index}
    return {2047}


class FixtureEmbedding:
    def embed(self, texts, deadline, *, before_call=None):
        if before_call:
            before_call()
        result = []
        for text in texts:
            ids = topics(text)
            vector = [0.0] * 2048
            for index in ids:
                vector[index] = 1 / len(ids)
            result.append(vector)
        return result

    def embed_query(self, text, deadline, *, before_call=None):
        return self.embed([text], deadline, before_call=before_call)[0]


class FixtureChat:
    calls = 0

    def complete(self, messages, deadline, *, before_call=None):
        self.calls += 1
        if before_call:
            before_call()
        payload = json.loads(messages[1]["content"])
        desired = topics(payload["question"])
        selected = [
            item for item in payload["evidence"] if topics(item["text"]) & desired
        ]
        covered = (
            set().union(*(topics(item["text"]) for item in selected))
            if selected
            else set()
        )
        if not desired <= covered:
            return {"insufficient": True, "claims": []}
        return {
            "insufficient": False,
            "claims": [
                {"text": item["text"], "evidence": [item["number"]]}
                for item in selected
            ],
        }


embedding = FixtureEmbedding()
chat = FixtureChat()
vectors = QdrantIndexClient(settings.qdrant_url, settings.qdrant_api_key, config)
indexing = IndexService(
    IndexRepository(engine),
    DatabaseError,
    embedding,
    vectors,
    IndexDependencyError,
    config.version,
)
retrieval = RetrievalService(
    RetrievalRepository(engine),
    DatabaseError,
    embedding,
    vectors,
    IndexDependencyError,
    auth.current,
    0.449357,
)
answers = AnswerService(retrieval, chat, IndexDependencyError, ChatProtocolError)
app = create_app(
    settings, auth=auth, indexing=indexing, retrieval=retrieval, answers=answers
)


def login(name):
    client = app.test_client()
    response = client.post(
        "/api/v1/auth/sessions",
        base_url=origin,
        headers=headers,
        json={"login_name": name, "password": os.environ["MYSQL_PASSWORD"]},
    )
    assert response.status_code == 200
    return client


def post(client, path, body):
    return client.post(
        path,
        base_url=origin,
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json=body,
    )


teachers = [login(f"eval_teacher_{i}") for i in range(2)]
students = [login(f"eval_student_{i}") for i in range(4)]
material_ids = {}
for index, material in enumerate(fixture["materials"]):
    teacher = teachers[index % 2]
    response = post(
        teacher,
        "/api/v1/materials",
        {"title": material["title"], "text": material["text"]},
    )
    assert response.status_code == 201
    material_ids[material["key"]] = response.json["data"]["id"]
    assert (
        post(
            teacher,
            "/api/v1/materials/" + response.json["data"]["id"] + "/index-builds",
            {},
        ).status_code
        == 201
    )
rows = []
for index, question in enumerate(fixture["questions"]):
    client = students[index % 4]
    expected = {material_ids[key] for key in question["expected_material_keys"]}
    for mode in ("keyword", "vector", "hybrid"):
        started = time.monotonic()
        found = post(
            client, "/api/v1/searches", {"query": question["question"], "mode": mode}
        )
        search_ms = (time.monotonic() - started) * 1000
        started = time.monotonic()
        answered = post(
            client,
            "/api/v1/material-answers",
            {"question": question["question"], "mode": mode},
        )
        answer_ms = (time.monotonic() - started) * 1000
        items = (
            found.json.get("data", {}).get("items", [])
            if found.status_code == 200
            else []
        )
        result = answered.json.get("data", {}) if answered.status_code == 200 else {}
        top_five = {item["material_id"] for item in items[:5]}
        cited = {item["material_id"] for item in result.get("citations", [])}
        hit = bool(expected & top_five)
        supported = (
            bool(expected)
            and expected <= cited
            and result.get("answer") != "资料中未找到相关内容"
        )
        refused = result.get("answer") == "资料中未找到相关内容" and not result.get(
            "citations"
        )
        rows.append(
            {
                "question_id": question["id"],
                "kind": question["kind"],
                "mode": mode,
                "has_answer": question["has_answer"],
                "http_search": found.status_code,
                "http_answer": answered.status_code,
                "hit_at_5": hit,
                "combined_coverage": bool(expected) and expected <= top_five,
                "supported_by_fixture": supported,
                "correct_refusal": refused,
                "search_ms": search_ms,
                "answer_ms": answer_ms,
                "top_five": [
                    {
                        "chunk_id": item["chunk_id"],
                        "material_id": item["material_id"],
                        "index_version": item["index_version"],
                    }
                    for item in items[:5]
                ],
            }
        )
        assert found.status_code == answered.status_code == 200, (
            question["id"],
            mode,
            found.status_code,
            answered.status_code,
        )
        assert cited <= expected, ("夹具引用了无关资料", question["id"], mode)
        if not question["has_answer"]:
            assert refused, ("无答案处理错误", question["id"], mode)


def timing(values):
    ordered = sorted(values)
    return {
        "samples": len(values),
        "median_ms": statistics.median(values),
        "p95_ms": ordered[math.ceil(0.95 * len(values)) - 1],
    }


summary = {}
for mode in ("keyword", "vector", "hybrid"):
    selected = [row for row in rows if row["mode"] == mode]
    positive = [row for row in selected if row["has_answer"]]
    negative = [row for row in selected if not row["has_answer"]]
    combined = [row for row in positive if row["kind"] == "combined"]
    summary[mode] = {
        "answerable": len(positive),
        "unanswerable": len(negative),
        "hit_at_5": sum(row["hit_at_5"] for row in positive) / len(positive),
        "fixture_support_rate": sum(row["supported_by_fixture"] for row in positive)
        / len(positive),
        "refusal_rate": sum(row["correct_refusal"] for row in negative) / len(negative),
        "combined_coverage_rate": sum(row["combined_coverage"] for row in combined)
        / len(combined),
        "failure_rate": sum(
            row["http_search"] != 200 or row["http_answer"] != 200 for row in selected
        )
        / len(selected),
        "search": timing([row["search_ms"] for row in selected]),
        "answer": timing([row["answer_ms"] for row in selected]),
    }
report = {
    "fixture": fixture["version"],
    "runtime": "真实MySQL/Qdrant；确定性嵌入与抽取式对话替身；Flask测试客户端",
    "final_course_evaluation": False,
    "human_review": "待全部功能完成后的最终验收",
    "threshold": 0.449357,
    "rrf_k": 60,
    "questions": len(fixture["questions"]),
    "summary": summary,
    "rows": rows,
}
print("EVAL_RESULT:" + json.dumps(report, ensure_ascii=False))
engine.dispose()
