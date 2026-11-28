import re
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


def test_ASJ_N01_submission_contract_is_202_location_and_no_score(candidate):
    client, auth, teaching = candidate
    auth.current.return_value.role = "student"
    teaching.submit.return_value = {
        "task_id": ID,
        "submission_id": ID,
        "quiz_id": ID,
        "status": "pending",
        "accepted_at": "2030-01-01T00:00:00+00:00",
        "started_at": None,
        "completed_at": None,
    }
    result = client.post(
        f"/api/v1/quizzes/{ID}/submissions",
        base_url=ORIGIN,
        headers={**HEADERS, "Idempotency-Key": "one"},
        json={"draft_revision": 0, "answers": {}},
    )
    assert result.status_code == 202 and result.json["code"] == 0
    assert result.json["data"] == teaching.submit.return_value
    assert result.headers["Location"] == f"/api/v1/submission-jobs/{ID}"
    assert result.headers["Cache-Control"] == "no-store"
    assert re.fullmatch(r"[0-9a-f]{32}", teaching.submit.call_args.args[-1])


def test_ASJ_F03_submission_job_is_read_through_identity(candidate):
    client, auth, teaching = candidate
    auth.current.return_value.role = "student"
    teaching.read_submission_job.return_value = {
        "task_id": ID,
        "submission_id": ID,
        "quiz_id": ID,
        "status": "running",
    }
    result = client.get(
        f"/api/v1/submission-jobs/{ID}", base_url=ORIGIN, headers=HEADERS
    )
    assert result.status_code == 200 and result.json["data"]["status"] == "running"
    assert teaching.read_submission_job.call_args.args[1] == ID
    assert result.headers["Cache-Control"] == "no-store"


def test_TSO_N01_teacher_score_override_contract(candidate):
    client, _, teaching = candidate
    teaching.override_score.return_value = {
        "submission_id": ID,
        "rule_score": 6,
        "score": 8,
        "score_source": "teacher_override",
        "reason": "复核步骤正确",
        "revision": 1,
    }
    result = client.put(
        f"/api/v1/quizzes/{ID}/submissions/{ID}/score-override",
        base_url=ORIGIN,
        headers=HEADERS,
        json={"expected_revision": 0, "score": 8, "reason": " 复核步骤正确 "},
    )
    assert result.status_code == 200 and result.json["code"] == 0
    assert result.json["data"]["score_source"] == "teacher_override"
    assert teaching.override_score.call_args.args[4:] == (0, 8, "复核步骤正确")


@pytest.mark.parametrize(
    "payload",
    [
        {"expected_revision": 0, "score": -1, "reason": "理由"},
        {"expected_revision": 0, "score": 1.5, "reason": "理由"},
        {"expected_revision": 0, "score": 1, "reason": " "},
        {"expected_revision": 0, "score": 1, "reason": "字" * 501},
        {"expected_revision": 0, "score": 1, "reason": "理由", "class_id": "x"},
    ],
)
def test_TSO_F01_invalid_override_rejected_before_service(candidate, payload):
    client, _, teaching = candidate
    result = client.put(
        f"/api/v1/quizzes/{ID}/submissions/{ID}/score-override",
        base_url=ORIGIN,
        headers=HEADERS,
        json=payload,
    )
    assert result.status_code == 400 and result.json["code"] == 1000
    teaching.override_score.assert_not_called()


def test_TSO_F02_student_cannot_override_score(candidate):
    client, auth, teaching = candidate
    auth.current.return_value.role = "student"
    result = client.put(
        f"/api/v1/quizzes/{ID}/submissions/{ID}/score-override",
        base_url=ORIGIN,
        headers=HEADERS,
        json={"expected_revision": 0, "score": 8, "reason": "合成理由"},
    )
    assert result.status_code == 403 and result.json["code"] == 1200
    teaching.override_score.assert_not_called()


def test_LI_F02_student_cannot_read_insights(candidate):
    client, auth, teaching = candidate
    auth.current.return_value.role = "student"
    result = client.get(f"/api/v1/quizzes/{ID}/insights", base_url=ORIGIN)
    assert result.status_code == 403 and result.json["code"] == 1200
    teaching.insights.assert_not_called()


def test_LI_F02_teacher_cannot_read_student_mistakes(candidate):
    client, _, teaching = candidate
    result = client.get(f"/api/v1/quizzes/{ID}/my-mistakes", base_url=ORIGIN)
    assert result.status_code == 403 and result.json["code"] == 1200
    teaching.my_mistakes.assert_not_called()


def test_mistake_explanation_session_uses_server_prompt_and_private_session(candidate):
    client, auth, teaching = candidate
    auth.current.return_value.role = "student"
    teaching.mistake_explanation_prompt.return_value = "服务端派生的安全开场"
    sessions = client.application.extensions["private_sessions"]
    sessions.create_for_builtin = Mock(
        return_value=(
            {
                "id": ID,
                "assistant_id": "assistant-a",
                "mode": "problem_guidance",
                "created_at": "2030-01-01T00:00:00Z",
                "updated_at": "2030-01-01T00:00:00Z",
                "expires_at": "2030-01-02T00:00:00Z",
            },
            False,
        )
    )

    result = client.post(
        f"/api/v1/quizzes/{ID}/mistakes/{ID}/explanation-sessions",
        base_url=ORIGIN,
        headers=HEADERS | {"Idempotency-Key": "mistake-session"},
        json={},
    )

    assert result.status_code == 201
    assert result.json["data"]["opening_question"] == "服务端派生的安全开场"
    teaching.mistake_explanation_prompt.assert_called_once()
    sessions.create_for_builtin.assert_called_once()
    assert sessions.create_for_builtin.call_args.args[2:] == (
        "mistake_explanation",
        b"mistake-session",
    )


@pytest.mark.parametrize(
    "headers,payload,status",
    [
        (HEADERS, {}, 400),
        (HEADERS | {"Idempotency-Key": "valid-key"}, {"answer": "A"}, 400),
    ],
)
def test_mistake_explanation_invalid_key_or_body_stops_before_services(
    candidate, headers, payload, status
):
    client, auth, teaching = candidate
    auth.current.return_value.role = "student"
    sessions = client.application.extensions["private_sessions"]
    sessions.create_for_builtin = Mock()

    result = client.post(
        f"/api/v1/quizzes/{ID}/mistakes/{ID}/explanation-sessions",
        base_url=ORIGIN,
        headers=headers,
        json=payload,
    )

    assert result.status_code == status
    assert not teaching.mock_calls and not sessions.create_for_builtin.mock_calls


def test_mistake_explanation_teacher_is_denied_before_context(candidate):
    client, _, teaching = candidate
    result = client.post(
        f"/api/v1/quizzes/{ID}/mistakes/{ID}/explanation-sessions",
        base_url=ORIGIN,
        headers=HEADERS | {"Idempotency-Key": "valid-key"},
        json={},
    )
    assert result.status_code == 403 and result.json["code"] == 1200
    teaching.mistake_explanation_prompt.assert_not_called()


def test_LI_F01_insights_rejects_unknown_filter(candidate):
    client, _, teaching = candidate
    result = client.get(
        f"/api/v1/quizzes/{ID}/insights?class_id=other", base_url=ORIGIN
    )
    assert result.status_code == 400 and result.json["code"] == 1000
    teaching.insights.assert_not_called()


def test_LI_F02_summary_pages_are_role_scoped(candidate):
    client, auth, _ = candidate
    assert client.get("/mistakes", base_url=ORIGIN).status_code == 403
    auth.current.return_value.role = "student"
    assert client.get("/console/dashboard", base_url=ORIGIN).status_code == 403
    assert client.get("/mistakes", base_url=ORIGIN).status_code == 200
