"""在生产形态的 TLS/NGINX/Gunicorn 入口核对工具状态、正文及降级。"""

import json
import math
import statistics
import time

from tests.integration.streaming_proxy_check import ROOT


def verify_tools(request, json_request, frame, cookies, compose, password):
    status, _, _, headers = json_request(
        "POST",
        "/api/v1/auth/sessions",
        body={"login_name": "sse_tool_teacher", "password": password},
    )
    assert status == 200
    teacher = next(
        value.split(";", 1)[0] for key, value in headers if key.lower() == "set-cookie"
    )

    def api(method, path, cookie=teacher, body=None, key=None, expected=200):
        code, reply, _, _ = json_request(
            method, path, cookie=cookie, body=body, key=key
        )
        assert code == expected, reply
        return reply["data"]

    assistant_id = api("GET", "/__session_fixture", cookie=cookies[10])["assistant_id"]
    connector = api(
        "POST",
        "/api/v1/tool-connectors",
        body={
            "alias": "proxy-math",
            "key": "teaching",
        },
        expected=201,
    )
    base = "/api/v1/tool-connectors/" + connector["id"]
    started = time.monotonic()
    api("POST", base + "/connections", body={})
    connection_ms = round((time.monotonic() - started) * 1000, 2)
    found = api("GET", base + "/tools")["items"]
    formula = next(tool for tool in found if tool["name"] == "formula_hint")
    api(
        "PATCH",
        base + "/tools/formula_hint",
        body={
            "fingerprint": formula["fingerprint"],
            "enabled": True,
        },
    )
    reference = "formula_hint@proxy-math"
    skill = api(
        "POST",
        "/api/v1/skills",
        body={
            "name": "代理工具验收",
            "enabled": True,
            "conditions": ["tool-proxy"],
            "tools": [reference],
            "steps": [{"type": "model", "instruction": "遵循资料依据。"}],
        },
        expected=201,
    )
    assistant_path = "/api/v1/assistants/" + assistant_id
    original = api("GET", assistant_path)
    config = {
        field: original[field]
        for field in ("name", "enabled", "material_ids", "skill_ids")
    }
    api(
        "PATCH",
        assistant_path,
        body=config
        | {
            "prompt": "",
            "revision": original["revision"],
            "skill_ids": config["skill_ids"] + [skill["id"]],
        },
    )
    samples = []
    captures = []

    def ask(index, scenario, expected, key=None):
        identifier = "tool-proxy-" + scenario
        cookie = cookies[index]
        session = api(
            "POST",
            "/api/v1/sessions",
            cookie=cookie,
            body={
                "assistant_id": assistant_id,
                "mode": "material_qa",
            },
            key="create-" + identifier,
            expected=201,
        )
        started = time.monotonic()
        connection, response = request(
            "POST",
            "/api/v1/sessions/" + session["id"] + "/messages",
            cookie=cookie,
            key=key or identifier,
            body={"question": "电压 " + identifier, "selected_tools": [reference]},
        )
        try:
            assert response.status == 200 and response.getheader(
                "Content-Type"
            ).startswith("text/event-stream")
            meta = frame(response)
            assert meta[0] == "meta"
            assert meta[1]["data"]["tools"][0]["status"] == expected
            delta = frame(response)
            first = (time.monotonic() - started) * 1000
            assert delta[0] == "delta" and delta[1]["data"]["text"] == "电压为24伏"
            done = frame(response)
            assert done[0] == "done" and done[1]["data"]["citations"] == [1]
            assert response.read() == b""
            total = (time.monotonic() - started) * 1000
        finally:
            connection.close()
        record = api("GET", "/api/v1/runs/" + done[1]["data"]["run_id"], cookie=cookie)
        assert record["result"]["tools"][0]["status"] == expected
        if expected == "succeeded":
            assert (
                record["result"]["tools"][0]["data"]["hint_id"]
                == "linear_equation:start"
            )
            samples.append({"first_ms": round(first, 2), "total_ms": round(total, 2)})
        captures.append(
            {
                "scenario": scenario,
                "events": [meta[0], delta[0], done[0]],
                "tool_status": expected,
            }
        )

    for index in range(10, 13):
        ask(index, str(index), "succeeded")
    audit = api("GET", "/api/v1/tool-call-audit")["items"]
    assert len(audit) == 3 and all(row["outcome"] == "succeeded" for row in audit)
    compose("stop", "mcp-server")
    try:
        assert json_request("GET", "/health")[0] == 200
        ask(13, "stopped", "error")
        api("DELETE", base + "/connections/current")
        ask(14, "disconnected", "rejected")
    finally:
        compose("rm", "--force", "--stop", "mcp-server")
        assistant = api("GET", assistant_path)
        api(
            "PATCH",
            assistant_path,
            body=config | {"prompt": "", "revision": assistant["revision"]},
        )

    def summary(values):
        ordered = sorted(values)
        return {
            "median": statistics.median(values),
            "p95": ordered[math.ceil(len(ordered) * 0.95) - 1],
        }

    report = {
        "samples": samples,
        "connect_ms": connection_ms,
        "tool_ms": summary([row["duration_ms"] for row in audit]),
        "first_ms": summary([row["first_ms"] for row in samples]),
        "total_ms": summary([row["total_ms"] for row in samples]),
        "frames": captures,
    }
    folder = ROOT / "reports/2026-11-04-add-controlled-mcp-tools"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "proxy-tools.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
