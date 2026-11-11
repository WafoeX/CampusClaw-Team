import json
import time
from dataclasses import replace

import pytest

from app.adapters.tool_protocol import PROTOCOL, ToolProtocol
from app.adapters.tool_transport import ToolDependencyError
from app.tool_config import load_tool_directory


@pytest.fixture
def teaching():
    return load_tool_directory(
        {"MCP_SERVICE_NETWORK": "172.20.0.0/24", "MCP_SERVICE_TOKEN": "test-token"}
    )["teaching"]


class Wire:
    def __init__(self, initialize=None, *, wrong_id=False, media="application/json"):
        self.initialize = initialize or {
            "protocolVersion": PROTOCOL,
            "capabilities": {"tools": {}},
        }
        self.calls = []
        self.wrong_id = wrong_id
        self.media = media

    def addresses(self, target, deadline):
        self.calls.append(("resolve", target.host))

    def request(
        self, target, method, path, deadline, *, headers, body=None, query=None, **_
    ):
        message = json.loads(body) if body else {}
        self.calls.append((method, path, headers, message, query))
        if method == "GET":
            return 200, {"Content-Type": self.media}, b'{"value": 20}'
        if method == "DELETE":
            return 204, {}, b""
        rpc = message["method"]
        if rpc == "notifications/initialized":
            return 202, {}, b""
        payload = {
            "initialize": self.initialize,
            "tools/list": {
                "tools": [
                    {
                        "name": "formula_hint",
                        "description": "提示",
                        "inputSchema": {"type": "object"},
                    }
                ]
            },
            "tools/call": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "hint_id": "linear_equation:start",
                                "hint": "先找出含未知数的项，考虑如何在等式两边做同一种运算。",
                            }
                        ),
                    }
                ],
                "isError": False,
            },
        }[rpc]
        response_id = "another-request" if self.wrong_id else message["id"]
        response = json.dumps({"jsonrpc": "2.0", "id": response_id, "result": payload})
        if rpc == "tools/list":
            data = ": keepalive\r\n\r\ndata: " + response + "\r\n\r\n"
            return 200, {"Content-Type": "text/event-stream"}, data.encode()
        return (
            200,
            {"Content-Type": "application/json", "Mcp-Session-Id": "synthetic-session"},
            response.encode(),
        )


def test_MP_B01_host_handles_post_sse_and_session(teaching):
    wire = Wire()
    protocol = ToolProtocol(wire)
    deadline = time.monotonic() + 1
    session, catalog = protocol.discover(teaching, deadline)
    assert session == "synthetic-session" and [row["name"] for row in catalog] == [
        "formula_hint"
    ]
    assert [row[3]["method"] for row in wire.calls] == [
        "initialize",
        "notifications/initialized",
        "tools/list",
    ]
    for _, path, headers, _, _ in wire.calls[1:]:
        assert path == "/mcp"
        assert headers["Mcp-Session-Id"] == session
        assert headers["MCP-Protocol-Version"] == PROTOCOL
    result = protocol.call(
        teaching,
        session,
        "formula_hint",
        {"topic": "linear_equation", "stage": "start"},
        deadline,
    )
    assert result["hint_id"] == "linear_equation:start"
    protocol.close(teaching, session, deadline)
    assert wire.calls[-1][0] == "DELETE"


@pytest.mark.parametrize(
    "kwargs",
    (
        {
            "initialize": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
            }
        },
        {"initialize": {"protocolVersion": PROTOCOL, "capabilities": {}}},
        {"wrong_id": True},
    ),
)
def test_MP_F05_unrecognized_version_capability_or_response_id(teaching, kwargs):
    wire = Wire(**kwargs)
    with pytest.raises(ToolDependencyError, match="protocol|response"):
        ToolProtocol(wire).discover(teaching, time.monotonic() + 1)
    assert len(wire.calls) == 1


def http_entry():
    return {
        "key": "fixture",
        "label": "只读夹具",
        "protocol": "http",
        "url": "https://catalog.example.test/base",
        "credential": "TOOL_TOKEN_FIXTURE",
        "tools": {
            "measure": {
                "description": "单位示例",
                "path": "/fixed",
                "modes": ["material_qa"],
                "parameters": {"unit": {"type": "string", "enum": ["cm"]}},
                "result": {"value": {"type": "number", "minimum": 0, "maximum": 100}},
            }
        },
    }


def test_CN_F01_TD_F01_TD_F04_read_only_http_fields_and_media():
    env = {
        "TOOL_CONNECTOR_DIRECTORY": json.dumps([http_entry()]),
        "TOOL_TOKEN_FIXTURE": "synthetic",
    }
    target = load_tool_directory(env)["fixture"]
    deadline = time.monotonic() + 1
    wire = Wire()
    protocol = ToolProtocol(wire)
    assert protocol.discover(target, deadline)[0] is None
    for invalid in ({"unit": "some-secret"}, {"unit": "cm", "text": "extra"}):
        with pytest.raises(ToolDependencyError, match="arguments"):
            protocol.call(target, None, "measure", invalid, deadline)
    with pytest.raises(ToolDependencyError, match="credential"):
        protocol.call(
            replace(target, token=""), None, "measure", {"unit": "cm"}, deadline
        )
    assert wire.calls == [("resolve", "catalog.example.test")]
    assert protocol.call(target, None, "measure", {"unit": "cm"}, deadline) == {
        "value": 20
    }
    assert wire.calls[-1] == (
        "GET",
        "/fixed",
        {"Accept": "application/json", "Authorization": "Bearer synthetic"},
        {},
        {"unit": "cm"},
    )
    wire.media = "text/html"
    with pytest.raises(ToolDependencyError, match="response"):
        protocol.call(target, None, "measure", {"unit": "cm"}, deadline)
    assert len(wire.calls) == 3

    invalid = http_entry() | {"url": "https://name@catalog.example.test/base"}
    with pytest.raises(ValueError, match="部署目录"):
        load_tool_directory({"TOOL_CONNECTOR_DIRECTORY": json.dumps([invalid])})


def test_CN_F05_transport_requires_all_candidates_to_be_approved(teaching):
    import socket

    from app.adapters.tool_transport import ToolTransport

    def resolve(host, port, *_):
        assert host == "mcp-server" and port == 8090
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("172.20.0.3", port)),
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("172.21.0.3", port)),
        ]

    wire = ToolTransport(resolve=resolve)
    with pytest.raises(ToolDependencyError, match="address"):
        wire.addresses(teaching, time.monotonic() + 1)
