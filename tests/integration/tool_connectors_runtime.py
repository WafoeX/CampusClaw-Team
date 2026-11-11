"""真实 MySQL 与同源 Cookie 验证连接管理及迟到发现。"""

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from uuid import uuid4

from werkzeug.security import generate_password_hash

from app import create_app
from app.adapters.ai_repository import AIRepository
from app.adapters.auth_repository import AuthRepository
from app.adapters.database import DatabaseError, IntegrityError, mysql_engine
from app.adapters.migrations.runner import migrate
from app.adapters.tool_repository import ToolRepository
from app.adapters.tool_transport import ToolDependencyError
from app.config import Settings
from app.services.ai_apps import AIApplicationService
from app.services.tool_connectors import ToolConnectors
from app.tool_config import load_tool_directory

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
password = os.environ["MYSQL_PASSWORD"]
AuthRepository(engine).seed_demo_accounts(
    generate_password_hash(password, method="scrypt")
)
directory = load_tool_directory(
    {
        "MCP_SERVICE_NETWORK": "172.20.0.0/24",
        "MCP_SERVICE_TOKEN": "synthetic-private-token",
    }
)
target = directory["teaching"]


class Fixture:
    def __init__(self):
        self.wire = self
        self.resolved = []
        self.sessions = []
        self.closed = []
        self.drift = False
        self.fail = False
        self.pause = False
        self.entered = Event()
        self.release = Event()

    def addresses(self, target, deadline):
        self.resolved.append(target.key)

    def discover(self, target, deadline):
        if self.pause:
            self.entered.set()
            assert self.release.wait(10)
        if self.fail:
            raise ToolDependencyError("upstream")
        session = uuid4().hex
        self.sessions.append(session)
        catalog = [policy.definition for policy in target.tools.values()]
        if self.drift:
            catalog[0] = catalog[0] | {"description": "修改后的教学提示"}
        return session, catalog

    def close(self, target, session, deadline):
        self.closed.append(session)


fixture = Fixture()
service = ToolConnectors(
    AIApplicationService(
        AIRepository(engine),
        DatabaseError,
        None,
        ToolDependencyError,
        ToolDependencyError,
        capacity=None,
        model_guard=None,
        quota=None,
    ),
    ToolRepository(),
    directory,
    fixture,
    ToolDependencyError,
    IntegrityError,
)
app = create_app(
    Settings.load(
        {**os.environ, "APP_PUBLIC_ORIGIN": origin}, Path("app/BUILD_VERSION")
    ),
    tool_connectors=service,
)


def login(name):
    client = app.test_client()
    result = client.post(
        "/api/v1/auth/sessions",
        base_url=origin,
        headers=headers,
        json={"login_name": name, "password": password},
    )
    assert result.status_code == 200
    return client


def request(client, method, path, value=None):
    kwargs = {"json": value} if value is not None else {}
    return client.open(path, method=method, base_url=origin, headers=headers, **kwargs)


teacher = login("demo_a_teacher")
student = login("demo_a_student")
outsider = login("demo_b_teacher")
assert teacher.get("/console/connectors", base_url=origin).status_code == 200
assert student.get("/console/connectors", base_url=origin).status_code == 403
options = request(teacher, "GET", "/api/v1/tool-connector-options")
assert options.json["data"]["items"] == [
    {
        "key": "teaching",
        "label": "本地教学工具",
        "protocol": "mcp",
        "credential_configured": True,
    }
]
assert (
    b"synthetic-private-token" not in options.data
    and b"MCP_SERVICE_TOKEN" not in options.data
)
base = "/api/v1/tool-connectors"
entry = {"alias": "math-fixture", "key": "teaching"}
assert request(student, "POST", base, entry).status_code == 403
for invalid in (
    entry | {"url": "https://other.example"},
    entry | {"key": "unknown"},
    entry | {"alias": "/bad"},
):
    result = request(teacher, "POST", base, invalid)
    assert result.status_code == 400 and result.json["code"] == 1000
assert fixture.resolved == []
assert request(teacher, "GET", base).json["data"]["total"] == 0
result = request(teacher, "POST", base, entry)
assert result.status_code == 201
row = result.json["data"]
assert row["credential_configured"] is True and row["status"] == "disconnected"
path = base + "/" + row["id"]
connection_path = path + "/connections"
disconnect_path = connection_path + "/current"
tools_path = path + "/tools"
assert request(outsider, "GET", base).json["data"]["items"] == []
other = request(outsider, "DELETE", disconnect_path)
missing = request(
    outsider, "DELETE", base + "/" + str(uuid4()) + "/connections/current"
)
assert (
    (other.status_code, other.json["code"], other.json["message"])
    == (missing.status_code, missing.json["code"], missing.json["message"])
    == (404, 1300, "资源不存在或不可访问")
)

assert request(teacher, "POST", connection_path, {}).status_code == 200
rows = request(teacher, "GET", tools_path).json["data"]["items"]
assert len(rows) == 2 and all(not item["enabled"] and item["allowed"] for item in rows)
for item in rows:
    result = request(
        teacher,
        "PATCH",
        tools_path + "/" + item["name"],
        {
            "fingerprint": item["fingerprint"],
            "enabled": True,
        },
    )
    assert result.status_code == 200 and result.json["data"]["enabled"] is True
assert request(teacher, "POST", connection_path, {}).status_code == 200
assert all(
    item["enabled"]
    for item in request(teacher, "GET", tools_path).json["data"]["items"]
)
fixture.drift = True
assert request(teacher, "POST", connection_path, {}).status_code == 200
changed = request(teacher, "GET", tools_path).json["data"]["items"]
assert len(changed) == 2 and not changed[0]["enabled"] and changed[1]["enabled"]
assert (
    request(
        teacher,
        "PATCH",
        tools_path + "/formula_hint",
        {
            "fingerprint": rows[0]["fingerprint"],
            "enabled": True,
        },
    ).status_code
    == 409
)

fixture.fail = True
assert request(teacher, "POST", connection_path, {}).status_code == 503
assert request(teacher, "GET", tools_path).json["data"]["items"] == []
fixture.fail = False
fixture.pause = True
with ThreadPoolExecutor() as executor:
    pending = executor.submit(request, teacher, "POST", connection_path, {})
    try:
        assert fixture.entered.wait(5)
        assert request(teacher, "DELETE", disconnect_path).status_code == 200
    finally:
        fixture.release.set()
    assert pending.result(timeout=10).status_code == 409
assert request(teacher, "GET", tools_path).json["data"]["items"] == []
assert fixture.sessions[-1] in fixture.closed
assert request(teacher, "DELETE", disconnect_path).status_code == 200
assert request(teacher, "DELETE", path).status_code == 200
assert request(teacher, "GET", path).status_code == 404
assert request(teacher, "POST", base, entry).status_code == 409
print("班级连接登记、发现、审阅、断开及并发边界通过")
