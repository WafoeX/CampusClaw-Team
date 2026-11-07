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
    auth, answers = Mock(), Mock()
    auth.current.return_value = SimpleNamespace(
        id="actor", class_id="class-a", role="student"
    )
    answers.answer.return_value = {"answer": "资料中未找到相关内容", "citations": []}
    client = create_app(
        replace(settings, public_origin=ORIGIN),
        auth=auth,
        materials=Mock(),
        chapters=Mock(),
        limiter=Mock(),
        retrieval=Mock(),
        answers=answers,
    ).test_client()
    client.set_cookie(COOKIE, "synthetic-session", domain="campusclaw.test")
    return client, auth, answers


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"question": " "},
        {"question": "x" * 4001},
        {"question": "资料", "class_id": "other"},
        {"question": "资料", "history": []},
        {"question": "资料", "evidence": []},
        {"question": "资料", "mode": "other"},
    ],
)
def test_QA_F01_invalid_question_never_enters_service(candidate, payload):
    client, _, answers = candidate
    response = client.post(
        "/api/v1/material-answers", base_url=ORIGIN, headers=HEADERS, json=payload
    )
    assert response.status_code == 400 and response.json["code"] == 1000
    answers.answer.assert_not_called()


def test_QA_F02_anonymous_answer_never_calls_service(candidate):
    client, auth, answers = candidate
    auth.current.return_value = None
    response = client.post(
        "/api/v1/material-answers",
        base_url=ORIGIN,
        headers=HEADERS,
        json={"question": "资料"},
    )
    assert response.status_code == 401
    answers.answer.assert_not_called()


def test_QA_B01_default_hybrid_and_no_history(candidate):
    client, _, answers = candidate
    response = client.post(
        "/api/v1/material-answers",
        base_url=ORIGIN,
        headers=HEADERS,
        json={"question": " 资料 "},
    )
    assert response.status_code == 200 and response.json["data"]["citations"] == []
    assert answers.answer.call_args.args[2:] == ("资料", "hybrid", None)
    assert response.headers["Cache-Control"] == "no-store"
