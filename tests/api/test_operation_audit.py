"""操作审计接口：任务过滤参数、角色拒绝与投影边界；真实班级过滤另见集成运行。"""

from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import MagicMock, Mock

import pytest

from app import create_app
from app.adapters.database import DatabaseError
from app.services.access import Identity
from app.services.ai_contracts import AI_CONFIGURE, AI_USE

ORIGIN = "https://campusclaw.test"
HEADERS = {"Origin": ORIGIN, "X-CampusClaw-Request": "same-origin"}
ID = "00000000-0000-0000-0000-000000000001"
CREATED = datetime(2026, 11, 20, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def audit_client(settings):
    repository = MagicMock()
    repository.list_operation_audit.return_value = ([], 0)
    repository.read_operation_audit.return_value = None
    ai_apps = Mock()
    ai_apps.repository = repository
    ai_apps.database_error = DatabaseError
    ai_apps.clock.return_value = CREATED
    app = create_app(
        replace(settings, public_origin=ORIGIN),
        auth=Mock(),
        materials=Mock(),
        chapters=Mock(),
        retrieval=Mock(),
        answers=Mock(),
        limiter=Mock(),
        ai_apps=ai_apps,
        resolve_identity=lambda: Identity(
            "teacher-a", "class-a", frozenset({AI_CONFIGURE})
        ),
    )
    return app.test_client(), repository


def list_audit(client, query=None, **options):
    return client.get(
        "/api/v1/operation-audits",
        base_url=ORIGIN,
        headers=HEADERS,
        query_string=query,
        **options,
    )


@pytest.mark.parametrize(
    "value",
    [
        "not-a-uuid",
        "00000000-0000-0000-0000-00000000000g",
        ID + "-extra",
        "",
    ],
)
def test_TJA_F06_invalid_job_id_rejects_without_query(audit_client, value):
    client, repository = audit_client
    result = list_audit(client, {"job_id": value})
    assert result.status_code == 400 and result.json["code"] == 1000
    assert not repository.list_operation_audit.called
    assert not repository.read_operation_audit.called


def test_TJA_F06_unknown_filter_rejects_without_query(audit_client):
    client, repository = audit_client
    result = list_audit(client, {"foo": ID})
    assert result.status_code == 400 and result.json["code"] == 1000
    assert not repository.list_operation_audit.called


def test_TJA_F05_student_cannot_read_audit(settings):
    repository = MagicMock()
    ai_apps = Mock()
    ai_apps.repository = repository
    ai_apps.database_error = DatabaseError
    app = create_app(
        replace(settings, public_origin=ORIGIN),
        auth=Mock(),
        materials=Mock(),
        chapters=Mock(),
        retrieval=Mock(),
        answers=Mock(),
        limiter=Mock(),
        ai_apps=ai_apps,
        resolve_identity=lambda: Identity("student-a", "class-a", frozenset({AI_USE})),
    )
    client = app.test_client()
    result = list_audit(client, {"job_id": ID})
    assert result.status_code == 403 and result.json["code"] == 1200
    assert not repository.list_operation_audit.called


def test_TJA_N03_job_filter_passes_to_repository_and_projects_only_metadata(
    audit_client,
):
    client, repository = audit_client
    row = {
        "id": ID,
        "class_id": "class-a",
        "request_id": "a" * 32,
        "actor_id": "teacher-a",
        "created_at": CREATED,
        "expires_at": CREATED,
        "action": "candidate_admit",
        "resource_type": "teaching_job",
        "resource_id": "11111111-1111-1111-1111-111111111111",
        "outcome": "succeeded",
        "skill_id": None,
        "total_tokens": None,
        "usage_status": "not_applicable",
        "duration_ms": 3,
        "event_json": '{"stem":"不得返回"}',
    }
    repository.list_operation_audit.return_value = ([row], 1)
    result = list_audit(client, {"job_id": ID})
    assert result.status_code == 200
    data = result.json["data"]
    assert data["total"] == 1
    item = data["items"][0]
    assert item == {
        "id": ID,
        "request_id": "a" * 32,
        "actor_id": "teacher-a",
        "created_at": "2026-11-20T12:00:00+00:00Z",
        "action": "candidate_admit",
        "resource_type": "teaching_job",
        "resource_id": "11111111-1111-1111-1111-111111111111",
        "outcome": "succeeded",
        "skill_id": None,
        "total_tokens": None,
        "usage_status": "not_applicable",
        "duration_ms": 3,
    }
    assert repository.list_operation_audit.call_args[0][-1] == ID


def test_TJA_F05_missing_and_cross_class_details_share_shape(audit_client):
    client, repository = audit_client
    path = f"/api/v1/operation-audits/{ID}"
    first = client.get(path, base_url=ORIGIN, headers=HEADERS)
    second = client.get(
        "/api/v1/operation-audits/22222222-2222-2222-2222-222222222222",
        base_url=ORIGIN,
        headers=HEADERS,
    )
    assert first.status_code == 404 and first.json["code"] == 1300
    assert second.status_code == 404 and second.json["code"] == 1300
    assert (
        first.json["code"],
        first.json["message"],
        first.json["data"],
    ) == (
        second.json["code"],
        second.json["message"],
        second.json["data"],
    )


def test_audit_page_teacher_renders_and_student_denied(settings):
    from types import SimpleNamespace

    auth = Mock()
    auth.current.return_value = SimpleNamespace(
        id="teacher-a",
        class_id="class-a",
        role="teacher",
        class_name="合成 A 班",
        login_name="teacher-a",
    )
    app = create_app(
        replace(settings, public_origin=ORIGIN),
        auth=auth,
        materials=Mock(),
        chapters=Mock(),
        retrieval=Mock(),
        answers=Mock(),
        limiter=Mock(),
        ai_apps=Mock(),
    )
    client = app.test_client()
    page = client.get("/console/audits", base_url=ORIGIN, headers=HEADERS)
    assert page.status_code == 200
    text = page.get_data(as_text=True)
    assert "audit-form" in text and "操作审计" in text
    auth.current.return_value = SimpleNamespace(
        id="student-a",
        class_id="class-a",
        role="student",
        class_name="合成 A 班",
        login_name="student-a",
    )
    denied = client.get("/console/audits", base_url=ORIGIN, headers=HEADERS)
    assert denied.status_code == 403 and denied.json["code"] == 1200
