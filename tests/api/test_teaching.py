from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app import create_app
from app.api.auth import COOKIE

ORIGIN = "https://campusclaw.test"
ID = "00000000-0000-0000-0000-000000000001"
HEADERS = {"Origin": ORIGIN, "X-CampusClaw-Request": "same-origin"}
QUESTION = {
    "kind": "single_choice",
    "stem": "合成题",
    "options": ["甲", "乙"],
    "answer": "A",
    "explanation": "合成解析",
}


@pytest.fixture
def candidate(settings):
    auth, teaching = Mock(), Mock()
    auth.current.return_value = SimpleNamespace(
        id="teacher",
        class_id="class-a",
        role="teacher",
        class_name="合成 A 班",
        login_name="teacher",
    )
    client = create_app(
        replace(settings, public_origin=ORIGIN),
        auth=auth,
        materials=Mock(),
        limiter=Mock(),
        chapters=Mock(),
        teaching=teaching,
    ).test_client()
    client.set_cookie(COOKIE, "fixture-session", domain="campusclaw.test")
    return client, auth, teaching


@pytest.mark.parametrize(
    "path", ["/api/v1/questions", f"/api/v1/questions/{ID}/reviews", "/api/v1/quizzes"]
)
def test_QB_F02_QZ_F02_student_cannot_manage(candidate, path):
    client, auth, teaching = candidate
    auth.current.return_value.role = "student"
    result = client.post(path, base_url=ORIGIN, headers=HEADERS, json={})
    assert result.status_code == 403 and result.json["code"] == 1200
    assert teaching.mock_calls == []


@pytest.mark.parametrize(
    "payload",
    [
        {**QUESTION, "options": ["同项", "同项"]},
        {**QUESTION, "answer": "C"},
        {**QUESTION, "kind": "essay"},
        {**QUESTION, "kind": []},
        {**QUESTION, "role": "teacher"},
    ],
)
def test_QB_F01_invalid_question_rejects_before_service(candidate, payload):
    client, _, teaching = candidate
    result = client.post(
        "/api/v1/questions", base_url=ORIGIN, headers=HEADERS, json=payload
    )
    assert result.status_code == 400 and result.json["code"] == 1000
    assert teaching.mock_calls == []


def test_QB_N01_valid_question_passes_normalized_fields(candidate):
    client, _, teaching = candidate
    teaching.create_question.return_value = {"id": ID}
    result = client.post(
        "/api/v1/questions",
        base_url=ORIGIN,
        headers=HEADERS,
        json={**QUESTION, "stem": " 合成题 "},
    )
    assert result.status_code == 201 and result.json["data"]["id"] == ID
    assert teaching.create_question.call_args.args[2]["stem"] == "合成题"


@pytest.mark.parametrize(
    "payload",
    [
        {
            "title": "空题",
            "chapter_id": None,
            "deadline_at": "2030-01-01T00:00:00Z",
            "answers_open_at": "2030-01-01T01:00:00Z",
            "items": [],
        },
        {
            "title": "分值",
            "chapter_id": None,
            "deadline_at": "2030-01-01T00:00:00Z",
            "answers_open_at": "2030-01-01T01:00:00Z",
            "items": [{"question_id": ID, "points": 101}],
        },
        {
            "title": "时间",
            "chapter_id": None,
            "deadline_at": "2030-01-01T00:00:00",
            "answers_open_at": "2030-01-01T01:00:00Z",
            "items": [{"question_id": ID, "points": 10}],
        },
    ],
)
def test_QZ_F01_invalid_configuration_has_no_write(candidate, payload):
    client, _, teaching = candidate
    result = client.post(
        "/api/v1/quizzes", base_url=ORIGIN, headers=HEADERS, json=payload
    )
    assert result.status_code == 400 and result.json["code"] == 1000
    assert teaching.mock_calls == []


def test_SB_F02_teacher_cannot_submit_and_anonymous_cannot_read(candidate):
    client, auth, teaching = candidate
    result = client.post(
        f"/api/v1/quizzes/{ID}/submissions",
        base_url=ORIGIN,
        headers={**HEADERS, "Idempotency-Key": "one"},
        json={"draft_revision": 0, "answers": {}},
    )
    assert result.status_code == 403 and result.json["code"] == 1200
    auth.current.return_value = None
    result = client.get(f"/api/v1/quizzes/{ID}/my-submission", base_url=ORIGIN)
    assert result.status_code == 401 and result.json["code"] == 1100
    assert teaching.mock_calls == []


def test_SB_N01_submission_contract_is_201_and_no_score(candidate):
    client, auth, teaching = candidate
    auth.current.return_value.role = "student"
    teaching.submit.return_value = {
        "submission_id": ID,
        "accepted_at": "2030-01-01T00:00:00+00:00",
    }
    result = client.post(
        f"/api/v1/quizzes/{ID}/submissions",
        base_url=ORIGIN,
        headers={**HEADERS, "Idempotency-Key": "one"},
        json={"draft_revision": 0, "answers": {}},
    )
    assert result.status_code == 201 and result.json["code"] == 0
    assert result.json["data"] == teaching.submit.return_value
    assert result.headers["Cache-Control"] == "no-store"
