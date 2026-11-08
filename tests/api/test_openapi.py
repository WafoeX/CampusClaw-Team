"""Task 5.1：文档与真实路由一致，沿用 Cookie 权限，无业务副作用。"""

import pytest

from app.api.openapi import ENDPOINTS, REQUESTS
from app.services.access import Identity
from app.services.ai_contracts import AI_USE
from tests.api.test_ai_apps import ORIGIN

pytest_plugins = ["tests.api.test_ai_apps"]


@pytest.mark.parametrize("path", ["/swagger", "/api/v1/openapi.json"])
def test_ST_F02_document_requires_identity(candidate, path):
    client, service, _ = candidate
    result = client.get(path, base_url=ORIGIN)
    assert result.status_code == 401 and result.json["code"] == 1100
    assert not service.mock_calls


def test_ST_N01_openapi_matches_routes_and_stream_contract(candidate):
    client, service, current = candidate
    current[0] = Identity("student", "a", frozenset({AI_USE}))
    result = client.get("/api/v1/openapi.json", base_url=ORIGIN)
    assert result.status_code == 200 and result.headers["Cache-Control"] == "no-store"
    spec = result.json
    operations = {
        op["operationId"]: op
        for methods in spec["paths"].values()
        for op in methods.values()
    }
    assert set(operations) == ENDPOINTS
    for rule in client.application.url_map.iter_rules():
        if rule.endpoint in ENDPOINTS:
            path = rule.rule
            for name in rule.arguments:
                path = path.replace("<" + name + ">", "{" + name + "}")
            for method in rule.methods - {"HEAD", "OPTIONS"}:
                assert (
                    spec["paths"][path][method.lower()]["operationId"] == rule.endpoint
                )
    for endpoint in REQUESTS:
        assert (
            operations[endpoint]["requestBody"]["content"]["application/json"]["schema"]
            == REQUESTS[endpoint]
        )
    stream = operations["send_private_message"]
    assert "text/event-stream" in stream["responses"]["200"]["content"]
    assert "application/json" in stream["responses"]["403"]["content"]
    assert {p["name"] for p in stream["parameters"]} == {
        "session_id",
        "Idempotency-Key",
        "X-CampusClaw-Request",
    }
    assert spec["servers"] == [{"url": "/"}]
    assert not service.mock_calls


def test_ST_N01_swagger_is_local_and_cookie_only(candidate):
    client, _, current = candidate
    current[0] = Identity("student", "a", frozenset({AI_USE}))
    result = client.get("/swagger", base_url=ORIGIN)
    text = result.get_data(as_text=True)
    assert result.status_code == 200
    assert "connect-src 'self'" in result.headers["Content-Security-Policy"]
    assert "credentials:'same-origin'" in text and "localStorage" not in text
    assert "textContent" in text and "innerHTML" not in text
    assert "new TextDecoder()" in text and "getReader()" in text
    assert 'src="https://' not in text and "最终验收 1.5" in text
