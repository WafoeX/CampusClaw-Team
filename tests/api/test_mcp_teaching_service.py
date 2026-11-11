import importlib
from pathlib import Path

import pytest

VERSION = "2025-06-18"
TOKEN = "synthetic-unit-test-token"
BASE_HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/json, text/event-stream",
    "MCP-Protocol-Version": VERSION,
}
SESSION_HEADER = "Mcp-Session-Id"
INITIALIZE = {
    "protocolVersion": VERSION,
    "capabilities": {},
    "clientInfo": {"name": "pytest", "version": "1"},
}


@pytest.fixture
def service(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "mcp-server"))
    monkeypatch.setenv("MCP_SERVICE_TOKEN", TOKEN)
    module = importlib.import_module("teaching_server")
    now = [0]
    return module.create_app(lambda: now[0]).test_client(), now, module


def rpc(client, method, params=None, *, headers=BASE_HEADERS, request_id=1):
    body = {"jsonrpc": "2.0", "method": method}
    if request_id is not None:
        body["id"] = request_id
    if params is not None:
        body["params"] = params
    return client.post("/mcp", json=body, headers=headers)


def initialize(client):
    initialized = rpc(client, "initialize", INITIALIZE)
    assert initialized.status_code == 200
    assert initialized.json["result"]["protocolVersion"] == VERSION
    headers = {**BASE_HEADERS, SESSION_HEADER: initialized.headers[SESSION_HEADER]}
    assert rpc(client, "tools/list", headers=headers).json["error"]["code"] == -32000
    notification = rpc(
        client, "notifications/initialized", headers=headers, request_id=None
    )
    assert notification.status_code == 202 and notification.data == b""
    return headers


def test_MP_N01_MP_B01_teaching_catalog_and_transport(service):
    client, _, _ = service
    assert client.get("/health").json == {"status": "ready"}
    headers = initialize(client)
    response = rpc(client, "tools/list", headers=headers, request_id="catalog")
    assert response.mimetype == "application/json"
    assert response.json["id"] == "catalog"
    tools = {tool["name"]: tool for tool in response.json["result"]["tools"]}
    assert set(tools) == {"formula_hint", "unit_convert"}
    for tool in tools.values():
        schema = tool["inputSchema"]
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])
    assert (
        client.get(
            "/mcp", headers={**headers, "Accept": "text/event-stream"}
        ).status_code
        == 405
    )
    assert client.delete("/mcp", headers=headers).status_code == 204
    assert rpc(client, "tools/list", headers=headers).status_code == 404


def test_MP_F01_bad_messages_and_arguments(service):
    client, _, _ = service
    headers = initialize(client)
    malformed = client.post(
        "/mcp",
        data='{"synthetic-marker":',
        content_type="application/json",
        headers=headers,
    )
    assert malformed.json["error"]["code"] == -32700
    assert b"synthetic-marker" not in malformed.data
    batch = client.post("/mcp", json=[{}], headers=headers)
    assert batch.json["error"]["code"] == -32600
    assert rpc(client, "unknown", headers=headers).json["error"]["code"] == -32601
    assert (
        rpc(
            client,
            "tools/list",
            headers={**headers, "MCP-Protocol-Version": "2024-11-05"},
        ).status_code
        == 400
    )

    args = {"value": 1, "from_unit": "m", "to_unit": "g"}
    response = rpc(
        client,
        "tools/call",
        {"name": "unit_convert", "arguments": args},
        headers=headers,
    )
    assert response.json["result"]["isError"] is True
    for invalid in (
        {**args, "marker": "synthetic-marker"},
        {**args, "value": True},
        {**args, "value": 0.0000001},
        {**args, "value": 1000001},
        {**args, "to_unit": ["cm"]},
    ):
        response = rpc(
            client,
            "tools/call",
            {"name": "unit_convert", "arguments": invalid},
            headers=headers,
        )
        assert response.json["error"]["code"] == -32602
        assert b"synthetic-marker" not in response.data


def test_MP_F02_MP_F03_auth_origin_and_expiry(service, monkeypatch):
    client, now, module = service
    invoked = []
    monkeypatch.setattr(module, "call_tool", lambda *args: invoked.append(args))
    headers = initialize(client)
    params = {
        "name": "formula_hint",
        "arguments": {"topic": "triangle_area", "stage": "check"},
    }
    for overrides, code in (
        ({"Authorization": ""}, 401),
        ({"Authorization": "Bearer wrong"}, 401),
        ({"Origin": "https://unapproved.example"}, 403),
        ({SESSION_HEADER: "nonexistent"}, 404),
    ):
        response = rpc(client, "tools/call", params, headers={**headers, **overrides})
        assert response.status_code == code
        assert TOKEN.encode() not in response.data
        assert SESSION_HEADER not in response.headers
    now[0] = module.SESSION_SECONDS
    assert rpc(client, "tools/list", headers=headers).status_code == 404
    assert rpc(client, "tools/call", params, headers=headers).status_code == 404
    assert invoked == []
    assert initialize(client)[SESSION_HEADER] != headers[SESSION_HEADER]


def test_MP_F02_requires_private_token(service, monkeypatch):
    _, _, module = service
    monkeypatch.delenv("MCP_SERVICE_TOKEN")
    with pytest.raises(RuntimeError, match="MCP_SERVICE_TOKEN"):
        module.create_app()
