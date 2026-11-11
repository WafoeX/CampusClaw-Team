"""仅通过 Compose 内网开放的教学 MCP 服务。"""

import hmac
import json
import os
import secrets
import threading
import time
from decimal import Decimal, InvalidOperation

from flask import Flask, Response, jsonify, request
from teaching_tools import TOOLS, call_tool

PROTOCOL_VERSION = "2025-06-18"
SESSION_HEADER = "Mcp-Session-Id"
MAX_BODY = 16 * 1024
MAX_SESSIONS = 512
SESSION_SECONDS = 1800

ERRORS = {
    -32700: "JSON 解析失败",
    -32600: "无效请求",
    -32601: "未知方法",
    -32602: "无效参数",
    -32000: "会话尚未初始化",
    -32001: "服务忙",
}


def rpc_error(code, request_id=None, status=200):
    return (
        jsonify(
            jsonrpc="2.0", id=request_id, error={"code": code, "message": ERRORS[code]}
        ),
        status,
    )


def parse_object(pairs):
    parsed = dict(pairs)
    if len(parsed) != len(pairs):
        raise ValueError
    return parsed


def invalid_constant(_value):
    raise ValueError


class Sessions:
    def __init__(self, clock):
        self.clock = clock
        self.sessions = {}
        self.lock = threading.Lock()

    def create(self):
        with self.lock:
            now = self.clock()
            self.sessions = {
                key: entry for key, entry in self.sessions.items() if entry[0] > now
            }
            if len(self.sessions) >= MAX_SESSIONS:
                return None
            key = secrets.token_urlsafe(32)
            self.sessions[key] = (now + SESSION_SECONDS, False)
            return key

    def access(self, key, action):
        with self.lock:
            entry = self.sessions.get(key)
            if entry is None:
                return None
            expires, initialized = entry
            if expires <= self.clock():
                del self.sessions[key]
                return None
            if action == "delete":
                del self.sessions[key]
                return True
            if action == "notifications/initialized":
                self.sessions[key] = (expires, True)
            return initialized


def valid_initialize(params):
    client = params.get("clientInfo")
    return (
        type(params.get("protocolVersion")) is str
        and isinstance(params.get("capabilities"), dict)
        and isinstance(client, dict)
        and all(
            isinstance(client.get(key), str) and client[key]
            for key in ("name", "version")
        )
    )


def create_app(clock=time.monotonic):
    token = os.environ.get("MCP_SERVICE_TOKEN", "")
    if not token or any(not 33 <= ord(character) <= 126 for character in token):
        raise RuntimeError("MCP_SERVICE_TOKEN 配置无效")
    authorization = f"Bearer {token}".encode("ascii")
    sessions = Sessions(clock)
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = MAX_BODY

    @app.get("/health")
    def health():
        return jsonify(status="ready")

    @app.route(
        "/mcp", methods=["GET", "POST", "DELETE"], provide_automatic_options=False
    )
    def endpoint():
        supplied = request.headers.get("Authorization", "").encode("utf-8")
        if not hmac.compare_digest(supplied, authorization):
            return Response(status=401, headers={"WWW-Authenticate": "Bearer"})
        if "Origin" in request.headers:
            return Response(status=403)
        if request.method in {"GET", "HEAD"}:
            return Response(status=405, headers={"Allow": "POST, DELETE"})
        session_id = request.headers.get(SESSION_HEADER)
        version = request.headers.get("MCP-Protocol-Version")
        if version is not None and version != PROTOCOL_VERSION:
            return Response(status=400)
        if request.method == "DELETE":
            return Response(
                status=204 if sessions.access(session_id, "delete") else 404
            )
        if request.mimetype != "application/json":
            return Response(status=415)
        if not all(
            request.accept_mimetypes[media] > 0
            for media in ("application/json", "text/event-stream")
        ):
            return Response(status=406)
        try:
            message = json.loads(
                request.get_data().decode("utf-8"),
                parse_float=Decimal,
                parse_constant=invalid_constant,
                object_pairs_hook=parse_object,
            )
        except (ValueError, InvalidOperation, RecursionError):
            return rpc_error(-32700, status=400)
        if (
            not isinstance(message, dict)
            or message.get("jsonrpc") != "2.0"
            or type(message.get("method")) is not str
            or ("id" in message and type(message["id"]) not in (int, str))
            or message.keys() - {"jsonrpc", "id", "method", "params"}
        ):
            return rpc_error(-32600, status=400)

        request_id = message.get("id")
        method = message["method"]
        params = message.get("params", {})
        if not isinstance(params, dict):
            return rpc_error(-32602, request_id, status=400)
        if method == "initialize":
            if (
                request_id is None
                or session_id is not None
                or not valid_initialize(params)
            ):
                return rpc_error(-32602, request_id, status=400)
            new_id = sessions.create()
            if new_id is None:
                return rpc_error(-32001, request_id, status=503)
            return (
                jsonify(
                    jsonrpc="2.0",
                    id=request_id,
                    result={
                        "protocolVersion": PROTOCOL_VERSION,
                        "serverInfo": {"name": "campusclaw-teaching", "version": "1.0"},
                        "capabilities": {"tools": {"listChanged": False}},
                    },
                ),
                200,
                {SESSION_HEADER: new_id},
            )
        if method == "notifications/initialized" and request_id is not None:
            return rpc_error(-32600, request_id, status=400)
        initialized = sessions.access(session_id, method)
        if initialized is None:
            return Response(status=404 if session_id else 400)
        if method == "notifications/initialized":
            return Response(status=202)
        if request_id is None:
            return Response(status=400)
        if method == "ping":
            result = {}
        elif not initialized:
            return rpc_error(-32000, request_id)
        elif method == "tools/list":
            if params.keys() - {"_meta"}:
                return rpc_error(-32602, request_id)
            result = {"tools": list(TOOLS.values())}
        elif method == "tools/call":
            if params.keys() - {"name", "arguments", "_meta"}:
                return rpc_error(-32602, request_id)
            try:
                result = call_tool(params.get("name"), params.get("arguments"))
            except ValueError:
                return rpc_error(-32602, request_id)
        else:
            return rpc_error(-32601, request_id)
        return jsonify(jsonrpc="2.0", id=request_id, result=result)

    return app
