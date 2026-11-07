from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app import create_app
from app.api.auth import COOKIE

ORIGIN = "https://campusclaw.test"
HEADERS = {"Origin": ORIGIN, "X-CampusClaw-Request": "same-origin"}


@pytest.fixture
def candidate(settings):
    auth, service = Mock(), Mock()
    auth.current.return_value = SimpleNamespace(
        id="actor", class_id="class-a", role="student"
    )
    service.search.return_value = {"mode": "keyword", "items": []}
    client = create_app(
        replace(settings, public_origin=ORIGIN),
        auth=auth,
        materials=Mock(),
        chapters=Mock(),
        limiter=Mock(),
        retrieval=service,
    ).test_client()
    client.set_cookie(COOKIE, "synthetic-session", domain="campusclaw.test")
    return client, auth, service


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"query": " "},
        {"query": "x" * 4001},
        {"query": "原文", "mode": "unknown"},
        {"query": "原文", "chapter_scope": None},
        {"query": "原文", "chapter_scope": ""},
        {"query": "原文", "class_id": "other"},
        {"query": "原文", "role": "teacher"},
        {"query": False},
    ],
)
def test_RT_F01_search_invalid_input_before_service(candidate, payload):
    client, _, service = candidate
    response = client.post(
        "/api/v1/searches", base_url=ORIGIN, headers=HEADERS, json=payload
    )
    assert response.status_code == 400 and response.json["code"] == 1000
    assert not service.mock_calls


def test_RT_F02_anonymous_search_does_not_recall(candidate):
    client, auth, service = candidate
    auth.current.return_value = None
    response = client.post(
        "/api/v1/searches", base_url=ORIGIN, headers=HEADERS, json={"query": "资料"}
    )
    assert response.status_code == 401 and response.json["data"] is None
    assert not service.mock_calls


def test_RT_B01_search_defaults_and_codepoint_boundary(candidate):
    client, _, service = candidate
    result = client.post(
        "/api/v1/searches",
        base_url=ORIGIN,
        headers=HEADERS,
        json={"query": " 😀" * 2000},
    )
    assert result.status_code == 200 and result.json["code"] == 0
    args = service.search.call_args.args
    assert args[2] == (" 😀" * 2000).strip() and args[3:] == ("keyword", None)
    assert result.headers["Cache-Control"] == "no-store"
