"""IX-F01/F02/F03：索引管理入口必须先授权再解析或访问服务。"""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app import create_app
from app.api.auth import COOKIE

ORIGIN = "https://campusclaw.test"
ID = "00000000-0000-0000-0000-000000000001"
PATH = "/api/v1/materials/" + ID + "/index-builds"
HEADERS = {
    "Origin": ORIGIN,
    "X-CampusClaw-Request": "same-origin",
    "Idempotency-Key": "build-key",
}


@pytest.fixture
def candidate(settings):
    auth, service = Mock(), Mock()
    auth.current.return_value = SimpleNamespace(
        id="actor", class_id="class-a", role="teacher"
    )
    service.status.return_value = {"items": []}
    service.run.return_value = ({"id": ID, "status": "published"}, 201)
    client = create_app(
        replace(settings, public_origin=ORIGIN),
        auth=auth,
        materials=Mock(),
        chapters=Mock(),
        limiter=Mock(),
        indexing=service,
    ).test_client()
    client.set_cookie(COOKIE, "synthetic-session", domain="campusclaw.test")
    return client, auth, service


@pytest.mark.parametrize(
    ("method", "path"), [("POST", PATH), ("GET", PATH), ("GET", PATH + "/" + ID)]
)
@pytest.mark.parametrize(
    ("role", "status", "code"), [("student", 403, 1200), (None, 401, 1100)]
)
def test_IX_F02_role_denied_before_index_service(
    candidate, method, path, role, status, code
):
    client, auth, service = candidate
    if role is None:
        auth.current.return_value = None
    else:
        auth.current.return_value.role = role
    response = client.open(
        path, method=method, base_url=ORIGIN, headers=HEADERS, json={}
    )
    assert response.status_code == status and response.json["code"] == code
    assert (
        response.json["data"] is None
        and response.headers["Cache-Control"] == "no-store"
    )
    assert not service.mock_calls


@pytest.mark.parametrize(
    "payload",
    [
        {"class_id": "class-b"},
        {"mode": "unknown"},
        {"mode": "custom", "window": True},
        {"mode": "custom", "window": 100, "overlap": 100},
        {"mode": "auto", "window": 100},
        {"mode": "title", "overlap": None},
        [],
    ],
)
def test_IX_F01_invalid_index_parameters_have_no_side_effect(candidate, payload):
    client, _, service = candidate
    response = client.post(PATH, base_url=ORIGIN, headers=HEADERS, json=payload)
    assert response.status_code == 400 and response.json["code"] == 1000
    assert not service.mock_calls


def test_IX_N01_index_entry_and_empty_state(candidate):
    client, _, service = candidate
    assert client.get(PATH, base_url=ORIGIN).json["data"] == {"items": []}
    result = client.post(PATH, base_url=ORIGIN, headers=HEADERS, json={})
    assert result.status_code == 201 and result.json["code"] == 0
    assert service.run.call_args.args[3] == b"build-key"
    assert "构建或重试索引" in client.get("/console", base_url=ORIGIN).text
