import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

from sqlalchemy import event, select
from sqlalchemy.exc import OperationalError

from app import create_app
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
    == 1
)
after = teacher.get(f"/api/v1/materials/{material_id}", base_url=origin).json["data"]
assert after["revision"] == 3 and after["chapter_id"] is None
assert (
    student.get(f"/api/v1/materials/{material_id}/download", base_url=origin).data
    == original
)
engine.dispose()
