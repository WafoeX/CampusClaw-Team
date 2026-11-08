"""SK-F01/F02：管理权限、同源防护、重复键和大小边界。"""

import pytest

from app.services.access import Identity
from app.services.ai_contracts import AI_CONFIGURE, AI_USE
from tests.api.test_ai_apps import HEADERS, ID, ORIGIN  # noqa: F401

pytest_plugins = ["tests.api.test_ai_apps"]


@pytest.fixture
def skill_candidate(candidate):
    return candidate


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/v1/skills"),
        ("POST", "/api/v1/skills"),
        ("GET", f"/api/v1/skills/{ID}"),
        ("PATCH", f"/api/v1/skills/{ID}"),
        ("DELETE", f"/api/v1/skills/{ID}"),
    ],
)
def test_SK_F02_anonymous_and_student_cannot_manage(skill_candidate, method, path):
    client, service, actor = skill_candidate
    for identity, status in [
        (None, 401),
        (Identity("student", "class", frozenset({AI_USE})), 403),
    ]:
        actor[0] = identity
        result = client.open(
            path, method=method, base_url=ORIGIN, headers=HEADERS, json={}
        )
        assert result.status_code == status and not service.mock_calls


@pytest.mark.parametrize(
    "data", ['{"name":"a","name":"b"}', '{"x":"' + "x" * 8192 + '"}']
)
def test_SK_F01_raw_duplicate_and_size_rejected(skill_candidate, data):
    client, service, actor = skill_candidate
    actor[0] = Identity("teacher", "class", frozenset({AI_USE, AI_CONFIGURE}))
    result = client.post(
        "/api/v1/skills",
        base_url=ORIGIN,
        headers=HEADERS,
        data=data,
        content_type="application/json",
    )
    assert result.status_code == 400 and not service.mock_calls
