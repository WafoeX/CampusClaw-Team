"""在隔离 Compose 的 app 容器验证独立工具服务及数据库副作用。"""

import json
import os
import socket
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pymysql

from app.adapters.tool_protocol import ToolProtocol
from app.adapters.tool_transport import ToolTransport
from app.tool_config import load_tool_directory


def verify():
    database = pymysql.connect(
        host=os.environ["MYSQL_HOST"],
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        database=os.environ["MYSQL_DATABASE"],
        connect_timeout=3,
    )

    def writes():
        with database.cursor() as cursor:
            cursor.execute(
                "SHOW GLOBAL STATUS WHERE Variable_name IN "
                "('Com_insert','Com_update','Com_delete','Com_replace')"
            )
            rows = dict(cursor.fetchall())
            assert len(rows) == 4
            return rows

    before = writes()
    with urlopen("http://mcp-server:8090/health", timeout=2) as response:
        assert json.load(response) == {"status": "ready"}
    endpoint = "http://mcp-server:8090/mcp"
    version = "2025-06-18"
    headers = {
        "Authorization": f"Bearer {os.environ['MCP_SERVICE_TOKEN']}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    for request_headers, code in (
        (headers | {"Authorization": "Bearer synthetic-wrong-token"}, 401),
        (headers, 400),
    ):
        try:
            urlopen(
                Request(endpoint, b'{"broken":', headers=request_headers), timeout=2
            ).close()
        except HTTPError as error:
            assert error.code == code
            assert "Mcp-Session-Id" not in error.headers
            response = error.read()
            assert os.environ["MCP_SERVICE_TOKEN"].encode() not in response
            if code == 400:
                assert json.loads(response)["error"]["code"] == -32700
        else:
            raise AssertionError("错误请求必须拒绝")

    def rpc(method, request_id=None, params=None):
        payload = {"jsonrpc": "2.0", "method": method}
        if request_id is not None:
            payload["id"] = request_id
        if params is not None:
            payload["params"] = params
        request = Request(endpoint, json.dumps(payload).encode(), headers=headers)
        with urlopen(request, timeout=2) as response:
            return response.status, response.read(), response.headers

    status, body, reply_headers = rpc(
        "initialize",
        1,
        {
            "protocolVersion": version,
            "capabilities": {},
            "clientInfo": {"name": "compose-check", "version": "1"},
        },
    )
    assert status == 200 and json.loads(body)["result"]["protocolVersion"] == version
    headers["Mcp-Session-Id"] = reply_headers["Mcp-Session-Id"]
    headers["MCP-Protocol-Version"] = version
    assert rpc("notifications/initialized")[:2] == (202, b"")
    status, body, reply_headers = rpc("tools/list", "catalog")
    result = json.loads(body)
    assert status == 200 and result["id"] == "catalog"
    assert reply_headers.get_content_type() == "application/json"
    assert {tool["name"] for tool in result["result"]["tools"]} == {
        "formula_hint",
        "unit_convert",
    }
    for request_id, (name, args, key, expected) in enumerate(
        (
            (
                "formula_hint",
                {"topic": "triangle_area", "stage": "start"},
                "hint_id",
                "triangle_area:start",
            ),
            (
                "unit_convert",
                {"value": 2.5, "from_unit": "m", "to_unit": "cm"},
                "value",
                "250",
            ),
        ),
        2,
    ):
        status, body, _ = rpc(
            "tools/call", request_id, {"name": name, "arguments": args}
        )
        result = json.loads(body)["result"]
        assert status == 200 and not result["isError"]
        assert json.loads(result["content"][0]["text"])[key] == expected
    try:
        urlopen(Request(endpoint, headers=headers, method="GET"), timeout=2).close()
    except HTTPError as error:
        assert error.code == 405
    else:
        raise AssertionError("GET 流应返回 405")
    ip = socket.gethostbyname("mcp-server")
    target = load_tool_directory(
        {
            "MCP_SERVICE_NETWORK": ip + "/32",
            "MCP_SERVICE_TOKEN": os.environ["MCP_SERVICE_TOKEN"],
        }
    )["teaching"]
    client = ToolProtocol(ToolTransport())
    session, discovered = client.discover(target, time.monotonic() + 2)
    assert {tool["name"] for tool in discovered} == {"formula_hint", "unit_convert"}
    assert client.call(
        target,
        session,
        "unit_convert",
        {"value": 25, "from_unit": "cm", "to_unit": "m"},
        time.monotonic() + 2,
    ) == {"factor": "0.01", "value": "0.25", "unit": "m"}
    client.close(target, session, time.monotonic() + 2)
    assert before == writes()
    database.close()
    print("教学服务内网调用通过")


if __name__ == "__main__":
    verify()
