from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app import create_app
from app.api.auth import COOKIE

ORIGIN = "https://campusclaw.test"
RESOURCE = "00000000-0000-0000-0000-000000000001"
HEADERS = {
    "Origin": ORIGIN,
    "X-CampusClaw-Request": "same-origin",
    "Idempotency-Key": "chapter-check",
}
WRITES = [
    ("POST", "/api/v1/chapters", {"name": "章节", "sort_order": 0}),
    ("PATCH", f"/api/v1/chapters/{RESOURCE}", {"name": "新名", "revision": 1}),
    ("DELETE", f"/api/v1/chapters/{RESOURCE}", {"revision": 1}),
    (
        "PUT",
        f"/api/v1/materials/{RESOURCE}/chapter-assignments/current",
        {"chapter_id": None, "revision": 1},
    ),
]


@pytest.fixture
def candidate(settings):
    auth, chapters = Mock(), Mock()
    auth.current.return_value = SimpleNamespace(
        id="actor", class_id="class-a", role="teacher"
    )
    client = create_app(
        replace(settings, public_origin=ORIGIN),
        auth=auth,
        materials=Mock(),
        limiter=Mock(),
        chapters=chapters,
    ).test_client()
    client.set_cookie(COOKIE, "fixture-session", domain="campusclaw.test")
    return client, auth, chapters


@pytest.mark.parametrize(("method", "path", "payload"), WRITES)
@pytest.mark.parametrize(
    ("role", "status", "code"), [("student", 403, 1200), (None, 401, 1100)]
)
def test_CH_F02_all_writes_reject_before_service(
    candidate, method, path, payload, role, status, code
):
    client, auth, chapters = candidate
    if role is None:
        auth.current.return_value = None
    else:
        auth.current.return_value.role = role
    result = client.open(
        path,
        method=method,
        base_url=ORIGIN,
        headers={**HEADERS, "X-Role": "teacher"},
        json=payload,
    )
    assert result.status_code == status
    assert result.json["code"] == code and result.json["data"] is None
    assert result.headers["Cache-Control"] == "no-store"
    assert result.json["request_id"] == result.headers["X-Request-ID"]
    assert chapters.mock_calls == []


@pytest.mark.parametrize(
    "payload",
    [
        {"name": " ", "sort_order": 0},
        {"name": "未分类", "sort_order": 0},
        {"name": "长" * 121, "sort_order": 0},
        {"name": "章节", "sort_order": True},
        {"name": "章节", "sort_order": -1},
        {"name": "章节", "sort_order": 1000001},
        {"name": "章节", "sort_order": 0, "class_id": "class-b"},
    ],
)
def test_CH_F01_invalid_creation_has_no_service_call(candidate, payload):
    client, _, chapters = candidate
    response = client.post(
        "/api/v1/chapters", base_url=ORIGIN, headers=HEADERS, json=payload
    )
    assert response.status_code == 400
    assert response.json["code"] == 1000 and response.json["data"] is None
    assert chapters.mock_calls == []


def test_CH_F01_invalid_assignment_uuid_has_no_service_call(candidate):
    client, _, chapters = candidate
    result = client.put(
        WRITES[-1][1],
        base_url=ORIGIN,
        headers=HEADERS,
        json={"chapter_id": "invalid", "revision": 1},
    )
    assert result.status_code == 400 and result.json["code"] == 1000
    assert chapters.mock_calls == []


@pytest.mark.parametrize(("method", "path", "payload"), WRITES)
def test_CH_F02_cross_origin_writes_reject_before_service(
    candidate, method, path, payload
):
    client, _, chapters = candidate
    result = client.open(
        path,
        method=method,
        base_url=ORIGIN,
        headers={**HEADERS, "Origin": "https://other.test"},
        json=payload,
    )
    assert result.status_code == 403 and result.json["code"] == 1200
    assert chapters.mock_calls == []
