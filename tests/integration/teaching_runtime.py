"""真实 MySQL：人工建题、发布快照、草稿和一次正式评分。"""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import quantiles
from threading import Barrier
from time import monotonic
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import event, func, insert, inspect, select, update
from sqlalchemy.exc import OperationalError
from werkzeug.security import generate_password_hash

from app import create_app
from app.adapters.auth_repository import AuthRepository
from app.adapters.auth_schema_v1 import accounts
from app.adapters.database import DatabaseError, mysql_engine
from app.adapters.migrations.runner import migrate
from app.adapters.teaching_repository import TeachingRepository
from app.adapters.teaching_schema_v10 import (
    quiz_items,
    quiz_participants,
    quiz_results,
    quiz_submissions,
    quizzes,
)
from app.config import Settings
from app.services.teaching import TeachingService

origin = "https://campusclaw.test"
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
with engine.connect() as connection:
    first_student = (
        connection.execute(
            select(accounts).where(accounts.c.login_name == "demo_a_student")
        )
        .mappings()
        .one()
    )
    teacher_b = (
        connection.execute(
            select(accounts).where(accounts.c.login_name == "demo_b_teacher")
        )
        .mappings()
        .one()
    )
second_id = str(uuid4())
teacher_name = "teaching_a_core_teacher"
created_at = datetime.now(UTC).replace(tzinfo=None)
with engine.begin() as connection:
    connection.execute(
        insert(accounts),
        [
            {
                "id": account_id,
                "login_name": login_name,
                "password_hash": first_student["password_hash"],
                "enabled": True,
                "class_id": first_student["class_id"],
                "role": role,
                "created_at": created_at,
                "updated_at": created_at,
            }
            for account_id, login_name, role in (
                (str(uuid4()), teacher_name, "teacher"),
                (second_id, "teaching_a_student_2", "student"),
            )
        ],
    )

app = create_app(
    Settings.load(
        {**os.environ, "APP_PUBLIC_ORIGIN": origin},
        Path(os.environ.get("CAMPUSCLAW_TEST_VERSION_FILE", "app/BUILD_VERSION")),
    ),
    teaching=TeachingService(TeachingRepository(engine), DatabaseError),
)
headers = {"Origin": origin, "X-CampusClaw-Request": "same-origin"}


def login(name, remote_ip=None):
    client = app.test_client()
    response = client.post(
        "/api/v1/auth/sessions",
        base_url=origin,
        headers=headers,
        json={"login_name": name, "password": os.environ["MYSQL_PASSWORD"]},
        **({"environ_base": {"REMOTE_ADDR": remote_ip}} if remote_ip else {}),
    )
    assert response.status_code == 200, response.json
    return client


def request(client, method, path, payload=None, *, key=None):
    options = {
        "base_url": origin,
        "headers": {**headers, **({"Idempotency-Key": key} if key else {})},
    }
    if payload is not None:
        options["json"] = payload
    return client.open(path, method=method, **options)


teacher = login(teacher_name)
student = login("demo_a_student")
student2 = login("teaching_a_student_2")
outsider = login("demo_b_teacher")
anonymous = app.test_client()
assert teacher.get("/console/questions", base_url=origin).status_code == 200
assert student.get("/console/questions", base_url=origin).status_code == 403
assert student.get("/quizzes", base_url=origin).status_code == 200

choice = {
    "kind": "single_choice",
    "stem": "甲与乙中哪项正确？",
    "options": ["甲", "乙"],
    "answer": "A",
    "explanation": "合成解析",
}
judgement = {
    "kind": "true_false",
    "stem": "合成判断题",
    "options": ["正确", "错误"],
    "answer": "false",
    "explanation": "合成解析",
}
assert request(student, "POST", "/api/v1/questions", choice).status_code == 403
assert request(anonymous, "POST", "/api/v1/questions", choice).status_code == 401
assert (
    request(teacher, "POST", "/api/v1/questions", {**choice, "answer": "C"}).status_code
    == 400
)
created = request(teacher, "POST", "/api/v1/questions", choice)
assert created.status_code == 201, created.json
question_id = created.json["data"]["id"]
second = request(teacher, "POST", "/api/v1/questions", judgement)
assert second.status_code == 201, second.json
second_question_id = second.json["data"]["id"]
assert request(outsider, "GET", f"/api/v1/questions/{question_id}").json["code"] == 1300
for target in (question_id, str(uuid4())):
    response = request(outsider, "GET", f"/api/v1/questions/{target}")
    assert (
        response.status_code,
        response.json["code"],
        response.json["message"],
        response.json["data"],
    ) == (404, 1300, "资源不存在或不可访问", None)
for identifier in (question_id, second_question_id):
    reviewed = request(
        teacher,
        "POST",
        f"/api/v1/questions/{identifier}/reviews",
        {"expected_version": 1},
    )
    assert reviewed.status_code == 200 and reviewed.json["data"]["reviewed"]

deadline = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
open_time = (datetime.now(UTC) + timedelta(hours=3)).isoformat()
quiz_payload = {
    "title": "合成测验",
    "chapter_id": None,
    "deadline_at": deadline,
    "answers_open_at": open_time,
    "items": [
        {"question_id": question_id, "points": 10},
        {"question_id": second_question_id, "points": 5},
    ],
}
assert (
    request(
        teacher, "POST", "/api/v1/quizzes", {**quiz_payload, "items": []}
    ).status_code
    == 400
)
created_quiz = request(teacher, "POST", "/api/v1/quizzes", quiz_payload)
assert created_quiz.status_code == 201, created_quiz.json
quiz_id = created_quiz.json["data"]["id"]
assert request(student, "GET", f"/api/v1/quizzes/{quiz_id}").status_code == 404
assert (
    request(student, "POST", f"/api/v1/quizzes/{quiz_id}/publications", {}).status_code
    == 403
)
published = request(teacher, "POST", f"/api/v1/quizzes/{quiz_id}/publications", {})
assert published.status_code == 200, published.json
assert len(published.json["data"]["items"]) == 2
empty_insights = request(teacher, "GET", f"/api/v1/quizzes/{quiz_id}/insights")
assert empty_insights.status_code == 200
assert empty_insights.json["data"]["participants"] == 2
assert empty_insights.json["data"]["submissions"] == 0
assert empty_insights.json["data"]["average_score"] is None
assert request(student, "GET", f"/api/v1/quizzes/{quiz_id}/insights").status_code == 403
assert (
    request(outsider, "GET", f"/api/v1/quizzes/{quiz_id}/insights").status_code == 404
)
item_one, item_two = (row["id"] for row in published.json["data"]["items"])
student_quiz = request(student, "GET", f"/api/v1/quizzes/{quiz_id}")
assert student_quiz.status_code == 200
assert all(
    "answer" not in item and "explanation" not in item
    for item in student_quiz.json["data"]["items"]
)
assert "合成解析" not in student_quiz.get_data(as_text=True)
assert request(outsider, "GET", f"/api/v1/quizzes/{quiz_id}").status_code == 404

# 编辑后的当前题重新待审，但已发布快照与冻结名单不变。
edited = request(
    teacher,
    "PATCH",
    f"/api/v1/questions/{question_id}",
    {**choice, "answer": "B", "expected_version": 1},
)
assert edited.status_code == 200 and not edited.json["data"]["reviewed"]
assert (
    request(teacher, "GET", f"/api/v1/quizzes/{quiz_id}").json["data"]["items"][0][
        "answer"
    ]
    == "A"
)
with engine.begin() as connection:
    later_id = str(uuid4())
    connection.execute(
        insert(accounts).values(
            id=later_id,
            login_name="teaching_late_student",
            password_hash=first_student["password_hash"],
            enabled=True,
            class_id=first_student["class_id"],
            role="student",
            created_at=datetime.now(UTC).replace(tzinfo=None),
            updated_at=datetime.now(UTC).replace(tzinfo=None),
        )
    )
late = login("teaching_late_student")
assert request(late, "GET", f"/api/v1/quizzes/{quiz_id}").status_code == 404

# 刷新/重新登录从服务器读回草稿；修订冲突拒绝覆盖。
saved = request(
    student,
    "PUT",
    f"/api/v1/quizzes/{quiz_id}/draft",
    {"draft_revision": 0, "answers": {item_one: "A"}},
)
assert saved.status_code == 200 and saved.json["data"]["revision"] == 1
again = login("demo_a_student")
draft = request(again, "GET", f"/api/v1/quizzes/{quiz_id}/draft")
assert draft.json["data"]["answers"] == {item_one: "A"}
assert (
    request(
        again,
        "PUT",
        f"/api/v1/quizzes/{quiz_id}/draft",
        {"draft_revision": 0, "answers": {}},
    ).status_code
    == 409
)
assert (
    request(
        again,
        "POST",
        f"/api/v1/quizzes/{quiz_id}/submissions",
        {"draft_revision": 1, "answers": {"bogus": "A"}},
        key="bad-answer",
    ).status_code
    == 400
)


# 评分写入失败必须回滚正式提交，恢复后只产生一份结果。
def fail_result(_conn, _cursor, statement, _parameters, _context, _many):
    if statement.startswith("INSERT INTO quiz_results"):
        raise OperationalError(statement, (), RuntimeError("synthetic score failure"))


event.listen(engine, "before_cursor_execute", fail_result)
try:
    failed = request(
        again,
        "POST",
        f"/api/v1/quizzes/{quiz_id}/submissions",
        {"draft_revision": 1, "answers": {item_one: "A", item_two: "false"}},
        key="final-one",
    )
    assert failed.status_code == 503 and failed.json["code"] == 1500
finally:
    event.remove(engine, "before_cursor_execute", fail_result)
with engine.connect() as connection:
    assert (
        connection.scalar(
            select(quiz_submissions.c.id).where(quiz_submissions.c.quiz_id == quiz_id)
        )
        is None
    )

after_failed_score = request(
    teacher, "GET", f"/api/v1/quizzes/{quiz_id}/insights"
).json["data"]
assert after_failed_score["submissions"] == 0
assert after_failed_score["average_score"] is None

submission_payload = {
    "draft_revision": 1,
    "answers": {item_one: "A", item_two: "false"},
}
first = request(
    again,
    "POST",
    f"/api/v1/quizzes/{quiz_id}/submissions",
    submission_payload,
    key="final-one",
)
assert first.status_code == 201 and set(first.json["data"]) == {
    "submission_id",
    "accepted_at",
}
replayed = request(
    again,
    "POST",
    f"/api/v1/quizzes/{quiz_id}/submissions",
    submission_payload,
    key="final-one",
)
assert replayed.status_code == 201 and replayed.json["data"] == first.json["data"]
assert (
    request(
        again,
        "POST",
        f"/api/v1/quizzes/{quiz_id}/submissions",
        submission_payload,
        key="new-key",
    ).json["code"]
    == 1401
)
assert (
    request(
        again,
        "POST",
        f"/api/v1/quizzes/{quiz_id}/submissions",
        {"draft_revision": 1, "answers": {}},
        key="final-one",
    ).json["code"]
    == 1400
)
before_open = request(again, "GET", f"/api/v1/quizzes/{quiz_id}/my-submission")
assert before_open.status_code == 200
assert (
    "score" not in before_open.json["data"]
    and "details" not in before_open.json["data"]
)
with engine.connect() as connection:
    assert (
        connection.scalar(
            select(quiz_results.c.score).where(
                quiz_results.c.submission_id == first.json["data"]["submission_id"]
            )
        )
        == 15
    )
    assert (
        connection.scalar(
            select(quiz_participants.c.student_id).where(
                quiz_participants.c.quiz_id == quiz_id,
                quiz_participants.c.student_id == later_id,
            )
        )
        is None
    )

# 测试夹具推进开放时刻；产品接口本身不允许修改已发布时间。
with engine.begin() as connection:
    connection.execute(
        update(quizzes)
        .where(quizzes.c.id == quiz_id)
        .values(
            answers_open_at=datetime.now(UTC).replace(tzinfo=None)
            - timedelta(seconds=1)
        )
    )
opened = request(again, "GET", f"/api/v1/quizzes/{quiz_id}/my-submission")
assert opened.status_code == 200 and opened.json["data"]["score"] == 15
assert opened.json["data"]["details"][0]["answer"] == "A"
mistakes = request(again, "GET", f"/api/v1/quizzes/{quiz_id}/my-mistakes")
assert mistakes.status_code == 200 and mistakes.json["data"] == {
    "open": True,
    "items": [],
}
insights = request(teacher, "GET", f"/api/v1/quizzes/{quiz_id}/insights")
assert insights.status_code == 200
assert insights.json["data"]["submission_rate"] == 50
assert insights.json["data"]["average_score"] == 15
assert all(
    item["correct_rate"] == 100 for item in insights.json["data"]["item_accuracy"]
)

# 新草稿包含未审核新修订时不得发布；重新审核后注入名单写失败，发布必须整笔回滚。
new_quiz = request(teacher, "POST", "/api/v1/quizzes", quiz_payload)
new_quiz_id = new_quiz.json["data"]["id"]
assert (
    request(teacher, "POST", f"/api/v1/quizzes/{new_quiz_id}/publications", {}).json[
        "code"
    ]
    == 1400
)
assert (
    request(
        teacher,
        "POST",
        f"/api/v1/questions/{question_id}/reviews",
        {"expected_version": 2},
    ).status_code
    == 200
)


def fail_publish(_conn, _cursor, statement, _parameters, _context, _many):
    if statement.startswith("INSERT INTO quiz_participants"):
        raise OperationalError(
            statement, (), RuntimeError("synthetic publication failure")
        )


event.listen(engine, "before_cursor_execute", fail_publish)
try:
    failed = request(teacher, "POST", f"/api/v1/quizzes/{new_quiz_id}/publications", {})
    assert failed.status_code == 503 and failed.json["code"] == 1500
finally:
    event.remove(engine, "before_cursor_execute", fail_publish)
with engine.connect() as connection:
    assert (
        connection.scalar(
            select(quizzes.c.published_at).where(quizzes.c.id == new_quiz_id)
        )
        is None
    )
    assert (
        connection.scalar(
            select(quiz_items.c.id).where(quiz_items.c.quiz_id == new_quiz_id)
        )
        is None
    )
    assert (
        connection.scalar(
            select(quiz_participants.c.student_id).where(
                quiz_participants.c.quiz_id == new_quiz_id
            )
        )
        is None
    )
assert (
    request(
        teacher, "POST", f"/api/v1/quizzes/{new_quiz_id}/publications", {}
    ).status_code
    == 200
)
new_item = request(student2, "GET", f"/api/v1/quizzes/{new_quiz_id}").json["data"][
    "items"
][0]["id"]

# 某学生参与行被锁住时，另一名学生仍能在截止前正式提交。
with engine.begin() as connection:
    connection.execute(
        select(quiz_participants)
        .where(
            quiz_participants.c.quiz_id == new_quiz_id,
            quiz_participants.c.student_id == second_id,
        )
        .with_for_update()
    ).one()
    start = monotonic()
    with ThreadPoolExecutor(max_workers=1) as pool:
        other = pool.submit(
            request,
            late,
            "POST",
            f"/api/v1/quizzes/{new_quiz_id}/submissions",
            {"draft_revision": 0, "answers": {new_item: "B"}},
            key="late-final",
        )
        assert other.result(timeout=2).status_code == 201
    assert monotonic() - start < 2
second_submit = request(
    student2,
    "POST",
    f"/api/v1/quizzes/{new_quiz_id}/submissions",
    {"draft_revision": 0, "answers": {new_item: "A"}},
    key="second-final",
)
assert second_submit.status_code == 201, second_submit.json
with engine.connect() as connection:
    assert (
        connection.scalar(
            select(quiz_results.c.score).where(
                quiz_results.c.submission_id
                == second_submit.json["data"]["submission_id"]
            )
        )
        == 0
    )
with engine.begin() as connection:
    connection.execute(
        update(quizzes)
        .where(quizzes.c.id == new_quiz_id)
        .values(
            answers_open_at=connection.scalar(select(func.utc_timestamp(6)))
            - timedelta(seconds=1)
        )
    )
wrong = request(student2, "GET", f"/api/v1/quizzes/{new_quiz_id}/my-mistakes")
assert wrong.status_code == 200
assert wrong.json["data"]["open"] is True
assert {item["item_id"] for item in wrong.json["data"]["items"]} == {
    item["id"]
    for item in request(student2, "GET", f"/api/v1/quizzes/{new_quiz_id}").json["data"][
        "items"
    ]
}
new_insights = request(teacher, "GET", f"/api/v1/quizzes/{new_quiz_id}/insights")
assert new_insights.status_code == 200
assert new_insights.json["data"]["participants"] == 3
assert new_insights.json["data"]["submissions"] == 2
assert new_insights.json["data"]["average_score"] == 5
assert new_insights.json["data"]["item_accuracy"][0]["correct_rate"] == 50

# 截止判定使用锁内数据库时钟，恰到截止时拒绝新提交。
cutoff_quiz = request(teacher, "POST", "/api/v1/quizzes", quiz_payload).json["data"][
    "id"
]
assert (
    request(
        teacher, "POST", f"/api/v1/quizzes/{cutoff_quiz}/publications", {}
    ).status_code
    == 200
)
with engine.begin() as connection:
    connection.execute(
        update(quizzes)
        .where(quizzes.c.id == cutoff_quiz)
        .values(deadline_at=connection.scalar(select(func.utc_timestamp(6))))
    )
cutoff = request(
    student2,
    "POST",
    f"/api/v1/quizzes/{cutoff_quiz}/submissions",
    {"draft_revision": 0, "answers": {}},
    key="cutoff",
)
assert cutoff.status_code == 409 and cutoff.json["code"] == 1402
with engine.begin() as connection:
    past = connection.scalar(select(func.utc_timestamp(6)))
    connection.execute(
        update(quizzes)
        .where(quizzes.c.id == quiz_id)
        .values(
            deadline_at=past - timedelta(seconds=2),
            answers_open_at=past - timedelta(seconds=1),
        )
    )
after_cutoff_replay = request(
    again,
    "POST",
    f"/api/v1/quizzes/{quiz_id}/submissions",
    submission_payload,
    key="final-one",
)
assert after_cutoff_replay.status_code == 201
assert after_cutoff_replay.json["data"] == first.json["data"]

# 截止前集中提交：八个不同学生同时冲击同一发布快照，逐人仅有一个结果。
burst_names = [f"teaching_burst_{index}" for index in range(8)]
with engine.begin() as connection:
    connection.execute(
        insert(accounts),
        [
            {
                "id": str(uuid4()),
                "login_name": name,
                "password_hash": first_student["password_hash"],
                "enabled": True,
                "class_id": first_student["class_id"],
                "role": "student",
                "created_at": datetime.now(UTC).replace(tzinfo=None),
                "updated_at": datetime.now(UTC).replace(tzinfo=None),
            }
            for name in burst_names
        ],
    )
burst_clients = [
    login(name, f"192.0.2.{index + 10}") for index, name in enumerate(burst_names)
]
burst_quiz = request(
    teacher,
    "POST",
    "/api/v1/quizzes",
    {**quiz_payload, "items": [{"question_id": question_id, "points": 10}]},
).json["data"]["id"]
assert (
    request(
        teacher, "POST", f"/api/v1/quizzes/{burst_quiz}/publications", {}
    ).status_code
    == 200
)
burst_item = request(burst_clients[0], "GET", f"/api/v1/quizzes/{burst_quiz}").json[
    "data"
]["items"][0]["id"]
barrier = Barrier(len(burst_clients))


def burst_submit(index, client):
    barrier.wait(timeout=10)
    started = monotonic()
    response = request(
        client,
        "POST",
        f"/api/v1/quizzes/{burst_quiz}/submissions",
        {"draft_revision": 0, "answers": {burst_item: "B"}},
        key=f"burst-{index}",
    )
    return response, (monotonic() - started) * 1000


with ThreadPoolExecutor(max_workers=len(burst_clients)) as pool:
    burst_responses, burst_ms = zip(
        *pool.map(burst_submit, range(8), burst_clients), strict=True
    )
assert all(response.status_code == 201 for response in burst_responses), [
    response.json for response in burst_responses
]
same_student_barrier = Barrier(2)


def repeat_burst(key):
    same_student_barrier.wait(timeout=10)
    return request(
        burst_clients[0],
        "POST",
        f"/api/v1/quizzes/{burst_quiz}/submissions",
        {"draft_revision": 0, "answers": {burst_item: "B"}},
        key=key,
    )


with ThreadPoolExecutor(max_workers=2) as pool:
    same_student = list(pool.map(repeat_burst, ("burst-0", "burst-extra")))
assert same_student[0].status_code == 201
assert same_student[0].json["data"] == burst_responses[0].json["data"]
assert same_student[1].status_code == 409 and same_student[1].json["code"] == 1401
with engine.connect() as connection:
    assert connection.scalar(
        select(func.count())
        .select_from(quiz_submissions)
        .where(quiz_submissions.c.quiz_id == burst_quiz)
    ) == len(burst_clients)
    assert connection.scalar(
        select(func.count())
        .select_from(quiz_results)
        .join(quiz_submissions, quiz_results.c.submission_id == quiz_submissions.c.id)
        .where(quiz_submissions.c.quiz_id == burst_quiz, quiz_results.c.score == 10)
    ) == len(burst_clients)

# LI-F05：删除资料只撤销错题出处，不改变已冻结的评分。
source = request(
    teacher,
    "POST",
    "/api/v1/materials",
    {"title": "错题来源", "text": "仅供合成测试的资料正文"},
    key="source-material",
).json["data"]["id"]
source_question = request(
    teacher,
    "POST",
    "/api/v1/questions",
    {**choice, "source_material_id": source},
).json["data"]["id"]
assert (
    request(
        teacher,
        "POST",
        f"/api/v1/questions/{source_question}/reviews",
        {"expected_version": 1},
    ).status_code
    == 200
)
source_quiz_response = request(
    teacher,
    "POST",
    "/api/v1/quizzes",
    {**quiz_payload, "items": [{"question_id": source_question, "points": 10}]},
)
assert source_quiz_response.status_code == 201, source_quiz_response.json
source_quiz = source_quiz_response.json["data"]["id"]
source_item = request(
    teacher, "POST", f"/api/v1/quizzes/{source_quiz}/publications", {}
).json["data"]["items"][0]["id"]
assert (
    request(
        again,
        "POST",
        f"/api/v1/quizzes/{source_quiz}/submissions",
        {"draft_revision": 0, "answers": {source_item: "B"}},
        key="wrong-with-source",
    ).status_code
    == 201
)
with engine.begin() as connection:
    connection.execute(
        update(quizzes)
        .where(quizzes.c.id == source_quiz)
        .values(
            answers_open_at=connection.scalar(select(func.utc_timestamp(6)))
            - timedelta(seconds=1)
        )
    )
before_delete = request(again, "GET", f"/api/v1/quizzes/{source_quiz}/my-mistakes")
assert before_delete.json["data"]["items"][0]["source_material_id"] == source
assert before_delete.json["data"]["items"][0]["source_snapshot"]["title"] == "错题来源"
summary = request(again, "GET", f"/api/v1/mistakes?quiz_id={source_quiz}&page_size=1")
assert summary.status_code == 200 and summary.json["data"]["total"] == 1
assert summary.json["data"]["items"][0]["items"] == before_delete.json["data"]["items"]
cross = request(outsider, "GET", f"/api/v1/learning-insights?quiz_id={source_quiz}")
missing = request(outsider, "GET", f"/api/v1/learning-insights?quiz_id={uuid4()}")
assert cross.status_code == missing.status_code == 404
assert cross.json["code"] == missing.json["code"] == 1300
assert request(teacher, "DELETE", f"/api/v1/materials/{source}").status_code == 200
after_delete = request(again, "GET", f"/api/v1/quizzes/{source_quiz}/my-mistakes")
assert after_delete.json["data"]["items"][0]["source_status"] == "unavailable"
assert after_delete.json["data"]["items"][0]["source_material_id"] is None
assert (
    request(again, "GET", f"/api/v1/quizzes/{source_quiz}/my-submission").json["data"][
        "score"
    ]
    == 0
)

# 合成库物理回退只移除本组结构，保留上游账号，再重升到 head。
with engine.connect() as connection:
    account_count = connection.scalar(select(func.count()).select_from(accounts))
config = Config()
config.set_main_option(
    "script_location", str(Path("app/adapters/migrations").resolve())
)
with engine.connect() as connection:
    config.attributes["connection"] = connection
    command.downgrade(config, "0009_app_configuration")
    connection.commit()
assert "quizzes" not in inspect(engine).get_table_names()
with engine.connect() as connection:
    assert (
        connection.scalar(select(func.count()).select_from(accounts)) == account_count
    )
migrate(engine)
migrate(engine)
assert "quizzes" in inspect(engine).get_table_names()
print(
    "teaching_submit_evidence",
    json.dumps(
        {
            "samples": len(burst_ms),
            "p95_ms": round(quantiles(burst_ms, n=20, method="inclusive")[-1], 2),
            "committed_submissions": len(burst_clients),
        }
    ),
)
print("TEACHING_RUNTIME_OK")
