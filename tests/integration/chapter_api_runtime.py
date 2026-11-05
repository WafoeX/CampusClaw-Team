import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

from sqlalchemy import event, insert, select
from sqlalchemy.exc import OperationalError

from app import create_app
from app.adapters.auth_schema_v1 import accounts
from app.adapters.chapter_repository import ChapterRepository
from app.adapters.chapter_schema_v4 import materials
from app.adapters.database import DatabaseError, mysql_engine
from app.adapters.material_schema_v2 import bodies
from app.api.auth import COOKIE
from app.config import Settings
from app.services.chapters import ChapterService

origin = "https://campusclaw.test"
engine = mysql_engine(
    host=os.environ["MYSQL_HOST"],
    port=int(os.environ["MYSQL_PORT"]),
    database=os.environ["MYSQL_DATABASE"],
    user=os.environ["MYSQL_USER"],
    password=os.environ["MYSQL_PASSWORD"],
)
app = create_app(
    Settings.load(
        {**os.environ, "APP_PUBLIC_ORIGIN": origin}, Path("app/BUILD_VERSION")
    ),
    chapters=ChapterService(ChapterRepository(engine), DatabaseError),
)
headers = {"Origin": origin, "X-CampusClaw-Request": "same-origin"}


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


teacher, student, outsider = (
    login("demo_a_teacher"),
    login("demo_a_student"),
    login("demo_b_teacher"),
)
anonymous = app.test_client()
assert student.get("/chapters", base_url=origin).status_code == 200
assert teacher.get("/chapters", base_url=origin).status_code == 200
assert anonymous.get("/chapters", base_url=origin).status_code == 303
with engine.connect() as connection:
    rows = connection.execute(select(materials.c.id, materials.c.class_id)).all()
    material_id = next(
        row.id
        for row in rows
        if row.class_id
        == teacher.get("/api/v1/auth/sessions/current", base_url=origin).json["data"][
            "class_id"
        ]
    )
    original = connection.scalar(
        select(bodies.c.content).where(bodies.c.material_id == material_id)
    )
chapters = "/api/v1/chapters"
create_headers = {**headers, "Idempotency-Key": "chapter-create"}
created = teacher.post(
    chapters,
    base_url=origin,
    headers=create_headers,
    json={"name": " 第一章 ", "sort_order": 0},
)
assert created.status_code == 201 and created.json["code"] == 0
chapter_id = created.json["data"]["id"]
assert (
    teacher.post(
        chapters,
        base_url=origin,
        headers=create_headers,
        json={"name": "第一章", "sort_order": 0},
    ).json["data"]
    == created.json["data"]
)
assert (
    teacher.post(
        chapters,
        base_url=origin,
        headers=create_headers,
        json={"name": "第二章", "sort_order": 0},
    ).status_code
    == 409
)
assert (
    student.get(chapters, base_url=origin).json["data"]["items"][0]["id"] == chapter_id
)
cookie = teacher.get_cookie(COOKIE, domain="campusclaw.test").value


def concurrent_create(_):
    worker = app.test_client()
    worker.set_cookie(COOKIE, cookie, domain="campusclaw.test")
    return worker.post(
        chapters,
        base_url=origin,
        headers={**headers, "Idempotency-Key": "chapter-concurrent"},
        json={"name": "并发章", "sort_order": 1},
    )


with ThreadPoolExecutor(max_workers=2) as pool:
    parallel = list(pool.map(concurrent_create, range(2)))
assert [response.status_code for response in parallel] == [201, 201]
assert parallel[0].json["data"] == parallel[1].json["data"]
assert (
    student.post(
        chapters,
        base_url=origin,
        headers={**create_headers, "X-Role": "teacher"},
        json={"name": "越权", "sort_order": 0},
    ).status_code
    == 403
)
assert (
    anonymous.post(
        chapters,
        base_url=origin,
        headers=create_headers,
        json={"name": "匿名", "sort_order": 0},
    ).status_code
    == 401
)
for bad in ({"name": " ", "sort_order": 0}, {"name": "溢出", "sort_order": 1000001}):
    assert (
        teacher.post(
            chapters,
            base_url=origin,
            headers={**headers, "Idempotency-Key": str(uuid4())},
            json=bad,
        ).status_code
        == 400
    )

assignment_url = f"/api/v1/materials/{material_id}/chapter-assignments/current"
assignment = {"chapter_id": chapter_id, "revision": 1}
assign_headers = {**headers, "Idempotency-Key": "chapter-assign"}
assigned = teacher.put(
    assignment_url, base_url=origin, headers=assign_headers, json=assignment
)
assert assigned.status_code == 200 and assigned.json["data"]["revision"] == 2
assert (
    teacher.put(
        assignment_url, base_url=origin, headers=assign_headers, json=assignment
    ).json["data"]
    == assigned.json["data"]
)
assert (
    teacher.put(
        assignment_url,
        base_url=origin,
        headers=assign_headers,
        json={"chapter_id": None, "revision": 1},
    ).status_code
    == 409
)
assert (
    teacher.put(
        assignment_url,
        base_url=origin,
        headers={**headers, "Idempotency-Key": "stale"},
        json=assignment,
    ).status_code
    == 409
)
assert (
    student.get(f"{chapters}/{chapter_id}/materials", base_url=origin).json["data"][
        "total"
    ]
    == 1
)
extra = teacher.post(
    "/api/v1/materials",
    base_url=origin,
    headers={**headers, "Idempotency-Key": "chapter-second-material"},
    json={"title": "未分类资料", "text": "保留在未分类的原文"},
)
assert extra.status_code == 201
extra_id = extra.json["data"]["id"]
assert (
    student.get(f"{chapters}/uncategorized/materials", base_url=origin).json["data"][
        "items"
    ][0]["id"]
    == extra_id
)

# CH-F05：两个独立教师账号同时使用同一修订，恰好一人成功。
with engine.begin() as connection:
    actor = dict(
        connection.execute(
            select(accounts).where(accounts.c.login_name == "demo_a_teacher")
        )
        .mappings()
        .one()
    )
    actor.update(id=str(uuid4()), login_name="chapter_second_teacher")
    connection.execute(insert(accounts).values(actor))
second_teacher = login("chapter_second_teacher")
target = teacher.post(
    chapters,
    base_url=origin,
    headers={**headers, "Idempotency-Key": "chapter-other-target"},
    json={"name": "另一章", "sort_order": 1},
)
assert target.status_code == 201
targets = [parallel[0].json["data"]["id"], target.json["data"]["id"]]
barrier = Barrier(2)


def competing_assignment(index):
    worker = (teacher, second_teacher)[index]
    barrier.wait(timeout=10)
    return worker.put(
        assignment_url,
        base_url=origin,
        headers={**headers, "Idempotency-Key": f"chapter-race-{index}"},
        json={"chapter_id": targets[index], "revision": 2},
    )


with ThreadPoolExecutor(max_workers=2) as pool:
    raced = list(pool.map(competing_assignment, range(2)))
assert sorted(response.status_code for response in raced) == [200, 409]
winner = next(
    index for index, response in enumerate(raced) if response.status_code == 200
)
assert raced[winner].json["data"]["revision"] == 3
replayed = (teacher, second_teacher)[winner].put(
    assignment_url,
    base_url=origin,
    headers={**headers, "Idempotency-Key": f"chapter-race-{winner}"},
    json={"chapter_id": targets[winner], "revision": 2},
)
assert (
    replayed.status_code == 200 and replayed.json["data"] == raced[winner].json["data"]
)
assert (
    teacher.get(f"/api/v1/materials/{material_id}", base_url=origin).json["data"][
        "revision"
    ]
    == 3
)
restored = teacher.put(
    assignment_url,
    base_url=origin,
    headers={**headers, "Idempotency-Key": "chapter-restore"},
    json={"chapter_id": chapter_id, "revision": 3},
)
assert restored.status_code == 200 and restored.json["data"]["revision"] == 4

# CH-N01/B01：同序稳定，改名调序生效，分页不重复且无另一班内容。
listing = student.get(chapters, base_url=origin).json["data"]["items"]
assert listing[-1]["id"] == "uncategorized"
assert listing[:-1] == sorted(
    listing[:-1], key=lambda row: (row["sort_order"], row["id"])
)
assert student.get(chapters, base_url=origin).json["data"]["items"] == listing
revised = teacher.patch(
    f"{chapters}/{targets[0]}",
    base_url=origin,
    headers=headers,
    json={"name": "排在最后", "sort_order": 1000000, "revision": 1},
)
assert revised.status_code == 200 and revised.json["data"]["revision"] == 2
assert (
    student.get(chapters, base_url=origin).json["data"]["items"][-2]["id"] == targets[0]
)

missing = str(uuid4())
foreign = outsider.get(f"{chapters}/{chapter_id}", base_url=origin)
absent = outsider.get(f"{chapters}/{missing}", base_url=origin)
assert foreign.status_code == absent.status_code == 404
for field in ("code", "message", "data"):
    assert foreign.json[field] == absent.json[field]
assert (
    teacher.put(
        assignment_url,
        base_url=origin,
        headers={**headers, "Idempotency-Key": "bad-scope"},
        json={"chapter_id": missing, "revision": 2},
    ).status_code
    == 404
)

# CH-F03：外班与缺失的读取、改名、删除、归类响应同构，且没有副作用。
outside_chapter = outsider.post(
    chapters,
    base_url=origin,
    headers={**headers, "Idempotency-Key": "outside-chapter"},
    json={"name": "B班目录", "sort_order": 0},
).json["data"]["id"]
before_scope = teacher.get(f"/api/v1/materials/{material_id}", base_url=origin).json[
    "data"
]
for verb in ("GET", "PATCH", "DELETE", "PUT"):
    denied = []
    for identifier in (outside_chapter, missing):
        path = f"{chapters}/{identifier}"
        body = {"revision": 1}
        if verb == "PATCH":
            body["name"] = "不应生效"
        if verb == "PUT":
            path = assignment_url
            body = {"chapter_id": identifier, "revision": 4}
        response = teacher.open(
            path,
            method=verb,
            base_url=origin,
            headers={**headers, "Idempotency-Key": str(uuid4())},
            **({} if verb == "GET" else {"json": body}),
        )
        assert response.status_code == 404 and response.json["code"] == 1300
        denied.append(
            {field: response.json[field] for field in ("code", "message", "data")}
        )
    assert denied[0] == denied[1]
foreign_material = next(row.id for row in rows if row.id != material_id)
response = teacher.put(
    f"/api/v1/materials/{foreign_material}/chapter-assignments/current",
    base_url=origin,
    headers={**headers, "Idempotency-Key": "foreign-material"},
    json={"chapter_id": chapter_id, "revision": 1},
)
assert response.status_code == 404 and response.json["code"] == 1300
assert (
    teacher.get(f"/api/v1/materials/{material_id}", base_url=origin).json["data"]
    == before_scope
)


def interrupt_delete(_conn, _cursor, statement, _parameters, _context, _many):
    if statement.startswith("DELETE FROM chapters"):
        raise OperationalError(None, None, RuntimeError("synthetic delete failure"))


before = teacher.get(f"/api/v1/materials/{material_id}", base_url=origin).json["data"]
event.listen(engine, "before_cursor_execute", interrupt_delete)
try:
    failed = teacher.delete(
        f"{chapters}/{chapter_id}",
        base_url=origin,
        headers=headers,
        json={"revision": 1},
    )
    assert failed.status_code == 503 and failed.json["code"] == 1500
finally:
    event.remove(engine, "before_cursor_execute", interrupt_delete)
assert (
    teacher.get(f"/api/v1/materials/{material_id}", base_url=origin).json["data"]
    == before
)
assert (
    teacher.delete(
        f"{chapters}/{chapter_id}",
        base_url=origin,
        headers=headers,
        json={"revision": 1},
    ).status_code
    == 200
)
assert student.get(f"{chapters}/{chapter_id}", base_url=origin).status_code == 404
assert (
    student.get(f"{chapters}/uncategorized/materials", base_url=origin).json["data"][
        "total"
    ]
    == 2
)
after = teacher.get(f"/api/v1/materials/{material_id}", base_url=origin).json["data"]
assert after["revision"] == 5 and after["chapter_id"] is None
assert (
    student.get(f"/api/v1/materials/{material_id}/download", base_url=origin).data
    == original
)

# CH-F05：持续竞争不同目标，避免偶发锁冲突被单次绿灯掩盖。
current_chapter = None
for round_number in range(12):
    destinations = [value for value in [None, *targets] if value != current_chapter]
    revision = after["revision"] + round_number
    barrier = Barrier(2)

    def repeat_competition(
        index,
        barrier=barrier,
        round_number=round_number,
        destinations=destinations,
        revision=revision,
    ):
        barrier.wait(timeout=10)
        return (teacher, second_teacher)[index].put(
            assignment_url,
            base_url=origin,
            headers={**headers, "Idempotency-Key": f"repeat-{round_number}-{index}"},
            json={"chapter_id": destinations[index], "revision": revision},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(repeat_competition, range(2)))
    assert sorted(response.status_code for response in outcomes) == [200, 409], (
        [(response.status_code, response.json["code"]) for response in outcomes],
    )
    current_chapter = next(
        response.json["data"]["chapter_id"]
        for response in outcomes
        if response.status_code == 200
    )
engine.dispose()
