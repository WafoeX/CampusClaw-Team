"""只复制进隔离容器/tmp的传输夹具；不进入应用镜像或生产路由。"""

import http.client
import json
import os
import select as socket_select
import socket
import sys
import threading
import time
from dataclasses import replace
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

from flask import g, request
from sqlalchemy import insert, select
from werkzeug.security import generate_password_hash

from app import create_app
from app.adapters.auth_repository import AuthRepository
from app.adapters.auth_schema_v1 import accounts, classes
from app.adapters.database import mysql_engine
from app.adapters.material_schema_v2 import bodies, materials
from app.api.http import success
from app.api.streaming import stream_response
from app.config import Settings
from app.services.access import AccessDenied
from app.services.answer_validation import validate_claims
from app.services.auth import utc_now
from app.services.streaming import ValidatedStream

DRAIN_MARKER = Path("/tmp/streaming-probe-draining")
EVIDENCE = [{"text": "电压为24伏，频率为50赫兹。"}]


def paragraph(text):
    return {"insufficient": False, "claims": [{"text": text, "evidence": [1]}]}


def serve_upstream():
    gates, completed, cancelled = {}, [], []
    active = set()
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, *_):
            pass

        def do_GET(self):
            if self.path == "/metrics":
                with lock:
                    value = {
                        "active": sorted(active),
                        "completed": list(completed),
                        "cancelled": list(cancelled),
                    }
                payload = json.dumps(value).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            identifier = self.path.removeprefix("/generate/")
            gate = threading.Event()
            with lock:
                gates[identifier] = gate
                active.add(identifier)
            finished = False
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.end_headers()
                self.wfile.write(
                    json.dumps(paragraph("电压为24伏"), ensure_ascii=False).encode()
                    + b"\n"
                )
                self.wfile.flush()
                until = time.monotonic() + 15
                while not gate.wait(0.02):
                    if time.monotonic() > until:
                        raise TimeoutError
                    if socket_select.select([self.connection], [], [], 0)[
                        0
                    ] and not self.connection.recv(1, socket.MSG_PEEK):
                        return
                output = (
                    paragraph("频率为50赫兹")
                    if not identifier.startswith("invalid")
                    else paragraph("电压为25伏")
                )
                self.wfile.write(
                    json.dumps(output, ensure_ascii=False).encode() + b"\n"
                )
                self.wfile.flush()
                finished = True
            except (OSError, TimeoutError):
                pass
            finally:
                with lock:
                    active.discard(identifier)
                    (completed if finished else cancelled).append(identifier)

        def do_POST(self):
            if self.path == "/chat/completions":
                payload = json.loads(
                    self.rfile.read(int(self.headers["Content-Length"]))
                )
                assert "未开放答案731" not in json.dumps(payload, ensure_ascii=False)
                assert "B班秘密资料" not in json.dumps(payload, ensure_ascii=False)
                data = json.loads(payload["messages"][1]["content"])
                identifier = data["question"].split()[-1]
                second = data["paragraph"] == 2
                gate = threading.Event()
                if second:
                    with lock:
                        gates[identifier] = gate
                        active.add(identifier)
                    until = time.monotonic() + 15
                    while not gate.wait(0.02):
                        if time.monotonic() > until:
                            return
                        if socket_select.select([self.connection], [], [], 0)[
                            0
                        ] and not self.connection.recv(1, socket.MSG_PEEK):
                            with lock:
                                active.discard(identifier)
                                cancelled.append(identifier)
                            return
                if identifier.startswith("dependency") and second:
                    with lock:
                        active.discard(identifier)
                        completed.append(identifier)
                    self.send_response(503)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                result = paragraph(
                    "电压为24伏"
                    if not second
                    else (
                        "电压为25伏"
                        if identifier.startswith("invalid")
                        else "频率为50赫兹"
                    )
                ) | {"more": not second}
                if second and identifier.startswith("protected"):
                    result = paragraph("未开放答案731") | {"more": False}
                if second and identifier.startswith("citation"):
                    result["claims"][0]["evidence"] = [2]
                value = json.dumps(
                    {
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": json.dumps(result, ensure_ascii=False),
                                },
                                "finish_reason": "stop",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(value)))
                self.end_headers()
                self.wfile.write(value)
                self.wfile.flush()
                if second:
                    with lock:
                        active.discard(identifier)
                        completed.append(identifier)
                return
            identifier = self.path.removeprefix("/release/")
            with lock:
                gate = gates.get(identifier)
                if gate:
                    gate.set()
            self.send_response(204)
            self.end_headers()

    ThreadingHTTPServer(("127.0.0.1", 9090), Handler).serve_forever()


def load_worker():
    settings = replace(
        Settings.load(os.environ, Path("app/BUILD_VERSION")),
        public_origin=os.environ["SSE_PROBE_ORIGIN"],
    )
    assert settings.mysql_database.startswith("campusclaw_test_")
    engine = mysql_engine(
        host=settings.mysql_host,
        port=settings.mysql_port,
        database=settings.mysql_database,
        user=settings.mysql_user,
        password=settings.mysql_password,
    )
    now = utc_now()
    class_id = str(uuid4())
    with engine.begin() as connection:
        connection.execute(
            insert(classes).values(
                id=class_id, code="sse-probe", name="流式合成班", created_at=now
            )
        )
        for index in range(20):
            connection.execute(
                insert(accounts).values(
                    id=str(uuid4()),
                    login_name=f"sse_student_{index}",
                    class_id=class_id,
                    role="student",
                    enabled=True,
                    password_hash=generate_password_hash(
                        os.environ["SSE_PROBE_PASSWORD"], method="scrypt"
                    ),
                    created_at=now,
                    updated_at=now,
                )
            )
        creator_id = connection.execute(
            select(accounts.c.id).where(accounts.c.class_id == class_id)
        ).first()[0]
        material_rows = [
            dict(
                id=str(uuid4()),
                class_id=class_id,
                creator_id=creator_id,
                title=f"容量资料{index}",
                sort_order=index,
                source_format="txt",
                media_type="text/plain",
                byte_size=len("合成容量资料".encode()),
                character_count=len("合成容量资料"),
                content_version=1,
                revision=1,
                created_at=now,
                updated_at=now,
            )
            for index in range(1000)
        ]
        connection.execute(insert(materials), material_rows)
        connection.execute(
            insert(bodies),
            [
                {"material_id": row["id"], "content": "合成容量资料".encode()}
                for row in material_rows
            ],
        )
    engine.dispose()
    app = create_app(
        settings,
        draining=DRAIN_MARKER.exists,
        policies={
            ("sse_probe", "POST"): "session",
            ("sse_probe_metrics", "GET"): "session",
            ("session_fixture", "GET"): "session",
            ("change_fixture", "POST"): "session",
        },
    )
    from session_proxy_worker import install

    install(app, engine, class_id, creator_id, material_rows[0]["id"])
    capacity = app.extensions["long_request_capacity"]
    committed, aborted = [], []

    def source(identifier, context):
        connection = http.client.HTTPConnection("127.0.0.1", 9090, timeout=15)
        try:
            context.check()
            connection.connect()
            upstream_socket = connection.sock
            context.on_cancel(lambda: upstream_socket.shutdown(socket.SHUT_RDWR))
            context.check()
            connection.request("GET", "/generate/" + identifier)
            response = connection.getresponse()
            if response.status != 200:
                raise OSError
            while line := response.readline(16385):
                context.check()
                if len(line) > 16384 or not line.endswith(b"\n"):
                    raise OSError
                yield json.loads(line)
        finally:
            connection.close()

    def validate(payload):
        text, _ = validate_claims(payload, EVIDENCE)
        return text + "\n"

    def validate_final(payloads, text):
        claims = [claim for payload in payloads for claim in payload["claims"]]
        combined, _ = validate_claims(
            {"insufficient": False, "claims": claims}, EVIDENCE
        )
        if combined + "\n" != text:
            raise AccessDenied(502, 1501, "输出校验失败")

    @app.post("/__sse_probe/<identifier>")
    def sse_probe(identifier):
        if (
            not identifier.replace("-", "").replace("_", "").isalnum()
            or len(identifier) > 64
        ):
            raise AccessDenied(400, 1000, "参数不合法")
        reservation = capacity.reserve()
        try:
            cookie = request.cookies.get("__Host-campusclaw_session")
            account_id = g.identity.subject_id

            def recheck():
                # 夹具使用与现有API同一当前身份查询，流中不访问Flask request/g。
                repo_engine = mysql_engine(
                    host=settings.mysql_host,
                    port=settings.mysql_port,
                    database=settings.mysql_database,
                    user=settings.mysql_user,
                    password=settings.mysql_password,
                )

                try:
                    row = AuthRepository(repo_engine).find_session(
                        sha256(cookie.encode()).digest(), utc_now()
                    )
                    if row is None or row["id"] != account_id:
                        raise AccessDenied(401, 1100, "登录状态无效")
                finally:
                    repo_engine.dispose()

            def commit(text):
                committed.append(identifier)
                return {"message_id": identifier, "text": text}

            stream = ValidatedStream(
                reservation,
                produce=lambda context: source(identifier, context),
                validate=validate,
                recheck=recheck,
                commit=commit,
                validate_final=validate_final,
                on_abort=lambda: aborted.append(identifier),
                metadata={"run_id": identifier, "citations": [1]},
                request_id=g.request_id,
            )
            return stream_response(stream)
        except Exception:
            reservation.release()
            raise

    @app.get("/__sse_probe_metrics")
    def sse_probe_metrics():
        return success(
            {"active": capacity.active, "committed": committed, "aborted": aborted}
        )

    return app


if __name__ == "__main__" and sys.argv[1:] == ["upstream"]:
    Path("/tmp/streaming-probe-upstream.pid").write_text(str(os.getpid()))
    serve_upstream()
