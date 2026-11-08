"""RT/IO：真实 MySQL 中文全文与 Qdrant，模型为明确确定性替身。"""

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Event
from uuid import uuid4

from sqlalchemy import func, insert, select
from werkzeug.security import check_password_hash, generate_password_hash

from app import create_app
from app.adapters.assistant_schema_v8 import messages as private_messages
from app.adapters.assistant_schema_v8 import runs as private_runs
from app.adapters.assistant_schema_v8 import sessions as private_sessions
from app.adapters.auth_repository import AuthRepository
from app.adapters.auth_schema_v1 import accounts, classes
from app.adapters.chapter_schema_v4 import chapters
from app.adapters.chat_client import ChatProtocolError
from app.adapters.database import DatabaseError, mysql_engine
from app.adapters.index_clients import IndexDependencyError, QdrantIndexClient
from app.adapters.index_repository import IndexRepository
from app.adapters.model_lease_repository import ModelLeaseRepository
from app.adapters.retrieval_repository import RetrievalRepository
from app.config import EmbeddingSettings, Settings
from app.services.answers import AnswerService
from app.services.auth import AuthService, utc_now
from app.services.indexing import IndexService
from app.services.model_gate import ModelGate
from app.services.retrieval import RetrievalService

engine = mysql_engine(
    host=os.environ["MYSQL_HOST"],
    port=int(os.environ["MYSQL_PORT"]),
    database=os.environ["MYSQL_DATABASE"],
    user=os.environ["MYSQL_USER"],
    password=os.environ["MYSQL_PASSWORD"],
)
assert engine.url.database.startswith("campusclaw_test_")
with engine.connect() as connection:
    private_before = [
        connection.scalar(select(func.count()).select_from(table))
        for table in (private_sessions, private_messages, private_runs)
    ]
phase = sys.argv[1]
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
repository = AuthRepository(engine)
if phase == "setup":
    now = utc_now()
    with engine.begin() as connection:
        class_ids = {section: str(uuid4()) for section in ("a", "b")}
        for section, class_id in class_ids.items():
            connection.execute(
                insert(classes).values(
                    id=class_id,
                    code="ret-" + section,
                    name="检索合成班" + section,
                    created_at=now,
                )
            )
        for name, section, role in [
            ("ret_a_teacher", "a", "teacher"),
            ("ret_a_student", "a", "student"),
            ("ret_b_teacher", "b", "teacher"),
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
auth = AuthService(
    repository,
    check_password_hash,
    generate_password_hash("synthetic-unused", method="scrypt"),
    DatabaseError,
)


class SyntheticEmbedding:
    fail = False

    def embed(self, texts, deadline, *, before_call=None):
        if before_call:
            before_call()
        if self.fail:
            raise IndexDependencyError("synthetic_failure")
        return [[1.0] + [0.0] * 2047 for _ in texts]

    def embed_query(self, text, deadline, *, before_call=None):
        return self.embed([text], deadline, before_call=before_call)[0]


embedding = SyntheticEmbedding()
vectors = QdrantIndexClient(settings.qdrant_url, settings.qdrant_api_key, config)
gate = ModelGate(ModelLeaseRepository(engine), DatabaseError)
indexing = IndexService(
    IndexRepository(engine),
    DatabaseError,
    embedding,
    vectors,
    IndexDependencyError,
    config.version,
    model_guard=gate.hold,
)
retrieval = RetrievalService(
    RetrievalRepository(engine),
    DatabaseError,
    embedding,
    vectors,
    IndexDependencyError,
    auth.current,
    0.449357,
    model_guard=gate.hold,
)


class SyntheticChat:
    calls = 0
    override = None
    unavailable = False
    messages = None

    def complete(self, messages, deadline, *, before_call=None):
        self.calls += 1
        self.messages = messages
        if before_call:
            before_call()
        if self.unavailable:
            raise IndexDependencyError("synthetic_chat_timeout")
        return (
            self.override
            if self.override is not None
            else {
                "insufficient": False,
                "claims": [{"text": "蓝鲸动力站的额定电压为24伏。", "evidence": [1]}],
            }
        )


chat = SyntheticChat()
answers = AnswerService(
    retrieval, chat, IndexDependencyError, ChatProtocolError, model_guard=gate.hold
)
app = create_app(
    settings, auth=auth, indexing=indexing, retrieval=retrieval, answers=answers
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
    login(name) for name in ("ret_a_teacher", "ret_a_student", "ret_b_teacher")
]


def post(client, path, fields, key=None):
    return client.post(
        path,
        base_url=origin,
        headers={**headers, "Idempotency-Key": key or str(uuid4())},
        json=fields,
    )


def search(query="蓝鲸", mode="keyword", scope=None):
    fields = {"query": query, "mode": mode}
    if scope is not None:
        fields["chapter_scope"] = scope
    return post(student, "/api/v1/searches", fields)


def put_chapter(material_id, chapter_id):
    revision = teacher.get("/api/v1/materials/" + material_id, base_url=origin).json[
        "data"
    ]["revision"]
    result = teacher.put(
        "/api/v1/materials/" + material_id + "/chapter-assignments/current",
        base_url=origin,
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={"chapter_id": chapter_id, "revision": revision},
    )
    assert result.status_code == 200


def citation_url(item):
    return (
        "/api/v1/materials/"
        + item["material_id"]
        + "/citations/"
        + item["chunk_id"]
        + "?source_version="
        + str(item["source_version"])
        + "&index_version="
        + str(item["index_version"])
    )


with engine.connect() as connection:
    class_a = connection.scalar(
        select(accounts.c.class_id).where(accounts.c.login_name == "ret_a_teacher")
    )
if phase == "setup":
    chapter_ids = []
    for title in ("力学", "空章节"):
        result = post(teacher, "/api/v1/chapters", {"name": title, "sort_order": 0})
        assert result.status_code == 201
        chapter_ids.append(result.json["data"]["id"])
    own = []
    for actor, title, text in [
        (
            teacher,
            "蓝鲸资料",
            "😀合成力学：蓝鲸动力站使用铝合金冷却片，额定电压为24伏。\r\n",
        ),
        (teacher, "植物资料", "合成植物：松林苗圃每周四灌溉。"),
        (outsider, "外班独有", "紫铜螺旋仪编号为887766。"),
    ]:
        created = post(actor, "/api/v1/materials", {"title": title, "text": text})
        assert created.status_code == 201
        item = created.json["data"]
        assert (
            post(
                actor, "/api/v1/materials/" + item["id"] + "/index-builds", {}
            ).status_code
            == 201
        )
        if actor is teacher:
            own.append(item["id"])
    put_chapter(own[0], chapter_ids[0])
    # 同一教师跨连接命名锁拒绝并发，其他学生独立，异常退出后可以重获。
    from app.services.access import AccessDenied, Identity

    actor = repository.find_account("ret_a_teacher")
    identity = Identity(actor.id, actor.class_id, frozenset())
    with gate.hold(identity):
        try:
            with gate.hold(identity):
                raise AssertionError("并发模型锁错误放行")
        except AccessDenied as error:
            assert error.status == 429
    with gate.hold(identity):
        pass
    # 范围、三路排名及出处码点逐字定位。
    for mode in ("keyword", "vector", "hybrid"):
        result = search(mode=mode, scope=chapter_ids[0])
        assert result.status_code == 200, (mode, result.status_code, result.json)
        assert {item["material_id"] for item in result.json["data"]["items"]} == {
            own[0]
        }
        item = result.json["data"]["items"][0]
        opened = student.get(citation_url(item), base_url=origin)
        assert opened.status_code == 200
        source = opened.json["data"]
        assert source["source_text"][item["start"] : item["end"]] == item["text"]
    # QA-N01/B01/F03/F04/F05：实际资料与出处，零调用及结构/数值失败。
    question = {
        "question": "蓝鲸动力站的额定电压是多少？",
        "mode": "keyword",
        "chapter_scope": chapter_ids[0],
    }
    answered = post(student, "/api/v1/material-answers", question)
    assert answered.status_code == 200 and answered.json["data"]["citations"]
    assert answered.json["data"]["answer"] == "蓝鲸动力站的额定电压为24伏。"
    before_empty_calls = chat.calls
    for no_answer in ("珊瑚天文台编号", "紫铜螺旋仪编号887766"):
        empty_answer = post(
            student,
            "/api/v1/material-answers",
            {"question": no_answer, "mode": "keyword"},
        )
        assert empty_answer.status_code == 200 and empty_answer.json["data"] == {
            "answer": "资料中未找到相关内容",
            "citations": [],
        }
    assert chat.calls == before_empty_calls
    chat.override = {
        "insufficient": False,
        "claims": [{"text": "蓝鲸动力站的额定电压为25伏。", "evidence": [1]}],
    }
    invalid = post(student, "/api/v1/material-answers", question)
    assert invalid.status_code == 502 and invalid.json["data"] is None
    chat.override = {
        "insufficient": False,
        "claims": [{"text": "蓝鲸动力站的额定电压为24伏。", "evidence": [99]}],
    }
    assert post(student, "/api/v1/material-answers", question).status_code == 502
    chat.override = None
    chat.unavailable = True
    timeout = post(student, "/api/v1/material-answers", question)
    assert timeout.status_code == 503 and timeout.json["data"] is None
    chat.unavailable = False
    # QA-F06：生成已取得证据，重建后不能返回旧答案或改指新片段。
    generation_entered, generation_release = Event(), Event()
    original_chat = chat.complete

    def pause_chat(*args, **kwargs):
        result = original_chat(*args, **kwargs)
        generation_entered.set()
        assert generation_release.wait(8)
        return result

    chat.complete = pause_chat
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(post, student, "/api/v1/material-answers", question)
        assert generation_entered.wait(8)
        assert (
            post(
                teacher, "/api/v1/materials/" + own[0] + "/index-builds", {}
            ).status_code
            == 201
        )
        generation_release.set()
        revoked = pending.result(timeout=10)
        assert revoked.status_code == 409 and revoked.json["data"] is None
    chat.complete = original_chat
    empty = search(mode="vector", scope=chapter_ids[1])
    assert empty.status_code == 200 and empty.json["data"]["items"] == []
    assert search(query="紫铜螺旋仪").json["data"]["items"] == []
    assert (
        search(query="蓝鲸", mode="keyword", scope="uncategorized").json["data"][
            "items"
        ]
        == []
    )
    foreign = post(
        outsider, "/api/v1/chapters", {"name": "外班章节", "sort_order": 0}
    ).json["data"]["id"]
    for scope in (foreign, str(uuid4())):
        rejected = search(scope=scope)
        assert rejected.status_code == 404 and rejected.json["code"] == 1300
    old = search(scope=chapter_ids[0]).json["data"]["items"][0]
    assert (
        post(teacher, "/api/v1/materials/" + own[0] + "/index-builds", {}).status_code
        == 201
    )
    assert student.get(citation_url(old), base_url=origin).status_code == 409
    # 在实际 Qdrant 返回之后移动资料，返回前范围重验必须拒绝缓存的旧证据。
    entered, release = Event(), Event()
    original = vectors.query

    def pause(*args):
        result = original(*args)
        entered.set()
        assert release.wait(8)
        return result

    vectors.query = pause
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(search, "蓝鲸", "vector", chapter_ids[0])
        assert entered.wait(8)
        put_chapter(own[0], chapter_ids[1])
        release.set()
        changed = pending.result(timeout=10)
        assert changed.status_code == 409
    vectors.query = original
    for mode in ("keyword", "vector", "hybrid"):
        assert search(mode=mode, scope=chapter_ids[0]).json["data"]["items"] == []
    # 首次仅关键词的资料使全班向量/混合明确失败，缩小到完整章节仍可用。
    new = post(
        teacher, "/api/v1/materials", {"title": "未就绪", "text": "仅关键词的合成资料"}
    ).json["data"]["id"]
    embedding.fail = True
    assert (
        post(teacher, "/api/v1/materials/" + new + "/index-builds", {}).status_code
        == 503
    )
    embedding.fail = False
    for mode in ("vector", "hybrid"):
        assert search(mode=mode).status_code == 503
        assert search(mode=mode, scope=chapter_ids[1]).status_code == 200
    assert search(mode="keyword", scope=chapter_ids[1]).status_code == 200
elif phase == "down":
    with engine.connect() as connection:
        scope = connection.scalar(
            select(chapters.c.id).where(
                chapters.c.class_id == class_a, chapters.c.name == "空章节"
            )
        )
    assert search(scope=scope).status_code == 200
    assert search(scope=scope).json["data"]["items"]
    before_calls = chat.calls
    for mode in ("vector", "hybrid"):
        unavailable_answer = post(
            student,
            "/api/v1/material-answers",
            {"question": "蓝鲸电压", "mode": mode, "chapter_scope": scope},
        )
        assert (
            unavailable_answer.status_code == 503
            and unavailable_answer.json["data"] is None
        )
    assert chat.calls == before_calls
    for mode in ("vector", "hybrid"):
        failed = search(mode=mode, scope=scope)
        assert failed.status_code == 503 and failed.json["code"] == 1500
elif phase == "delete":
    with engine.connect() as connection:
        scope = connection.scalar(
            select(chapters.c.id).where(
                chapters.c.class_id == class_a, chapters.c.name == "空章节"
            )
        )
    item = search(scope=scope).json["data"]["items"][0]
    assert (
        teacher.delete(
            "/api/v1/materials/" + item["material_id"], base_url=origin, headers=headers
        ).status_code
        == 200
    )
    for mode in ("keyword", "vector", "hybrid"):
        result = search(mode=mode, scope=scope)
        assert result.status_code == 200 and result.json["data"]["items"] == []
    assert student.get(citation_url(item), base_url=origin).status_code == 404
    vectors.endpoint.request("DELETE", vectors.path, None, time.monotonic() + 15)
with engine.connect() as connection:
    private_after = [
        connection.scalar(select(func.count()).select_from(table))
        for table in (private_sessions, private_messages, private_runs)
    ]
assert private_after == private_before, "ST-N02：单次问答不得新增会话、消息或执行记录"
engine.dispose()
