"""AP权限、同源、请求白名单与零服务调用；数据库副作用另做真实集成。"""

from unittest.mock import Mock

import pytest

from app.services.access import Identity
from app.services.ai_contracts import AI_CONFIGURE, AI_USE

ORIGIN = "https://campusclaw.test"
HEADERS = {
    "Origin": ORIGIN,
    "X-CampusClaw-Request": "same-origin",
    "Idempotency-Key": "api-test",
}
ID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def candidate(settings):
    from dataclasses import replace

    service = Mock()
    service.catalogue.return_value = {"items": []}
    identity = [None]
    from app import create_app

    app = create_app(
        replace(settings, public_origin=ORIGIN),
        auth=Mock(),
        materials=Mock(),
        chapters=Mock(),
        retrieval=Mock(),
        answers=Mock(),
        limiter=Mock(),
        ai_apps=service,
        resolve_identity=lambda: identity[0],
    )
    return app.test_client(), service, identity


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/v1/ai-apps"),
        ("GET", "/api/v1/runs"),
        ("GET", f"/api/v1/runs/{ID}"),
        ("POST", "/api/v1/prompt-templates"),
        ("POST", f"/api/v1/prompt-templates/{ID}/previews"),
        ("POST", "/api/v1/ai-apps/polish/runs"),
        ("PATCH", f"/api/v1/assistants/{ID}"),
    ],
)
def test_AP_F02_anonymous_never_enters_service(candidate, method, path):
    client, service, _ = candidate
    response = client.open(
        path, method=method, base_url=ORIGIN, headers=HEADERS, json={}
    )
    assert response.status_code == 401 and response.json["code"] == 1100
    assert not service.mock_calls


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/api/v1/prompt-templates"),
        ("PATCH", f"/api/v1/prompt-templates/{ID}"),
        ("DELETE", f"/api/v1/prompt-templates/{ID}"),
        ("POST", "/api/v1/assistants"),
        ("PATCH", f"/api/v1/assistants/{ID}"),
    ],
)
def test_AP_F02_student_cannot_write_configuration(candidate, method, path):
    client, service, current = candidate
    current[0] = Identity("student", "class", frozenset({AI_USE}))
    result = client.open(path, method=method, base_url=ORIGIN, headers=HEADERS, json={})
    assert result.status_code == 403 and not service.mock_calls


def test_AP_N01_catalogue_no_store(candidate):
    client, service, current = candidate
    current[0] = Identity("student", "class", frozenset({AI_USE}))
    result = client.get("/api/v1/ai-apps", base_url=ORIGIN)
    assert (
        result.json["data"] == {"items": []}
        and result.headers["Cache-Control"] == "no-store"
    )
    service.catalogue.assert_called_once_with(current[0])


@pytest.mark.parametrize(
    "payload",
    [
        '{"revision":1,"revision":2,"variables":{"input":"x"}}',
        '{"revision":1,"variables":{},"class_id":"b"}',
    ],
)
def test_AP_F01_duplicate_and_unknown_fields_rejected(candidate, payload):
    client, service, current = candidate
    current[0] = Identity("student", "class", frozenset({AI_USE}))
    result = client.post(
        f"/api/v1/prompt-templates/{ID}/previews",
        base_url=ORIGIN,
        headers=HEADERS,
        data=payload,
        content_type="application/json",
    )
    assert result.status_code == 400 and not service.mock_calls


def test_AP_F02_wrong_origin_cannot_create_configuration(candidate):
    client, service, current = candidate
    current[0] = Identity("teacher", "class", frozenset({AI_USE, AI_CONFIGURE}))
    result = client.post(
        "/api/v1/assistants",
        base_url=ORIGIN,
        headers={**HEADERS, "Origin": "https://other.test"},
        json={},
    )
    assert result.status_code == 403 and not service.mock_calls
