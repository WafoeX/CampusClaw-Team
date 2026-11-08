"""FB-F02/F03：本人出处、评价及教师队列入口在业务层之前拒绝。"""

import pytest

from app.services.access import Identity
from app.services.ai_contracts import AI_USE
from tests.api.test_ai_apps import HEADERS, ID, ORIGIN

pytest_plugins = ["tests.api.test_ai_apps"]
CITATION = f"/api/v1/sessions/{ID}/messages/{ID}/citations/1"
FEEDBACK = f"/api/v1/sessions/{ID}/messages/{ID}/feedback"


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", CITATION),
        ("PUT", FEEDBACK),
        ("GET", "/api/v1/teaching-feedback"),
        ("PATCH", "/api/v1/teaching-feedback/" + ID),
    ],
)
def test_FB_F02_anonymous_has_no_data_or_calls(candidate, method, path):
    client, service, _ = candidate
    result = client.open(path, method=method, base_url=ORIGIN, headers=HEADERS, json={})
    assert result.status_code == 401 and result.json["code"] == 1100
    assert not service.mock_calls


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/v1/teaching-feedback"),
        ("PATCH", "/api/v1/teaching-feedback/" + ID),
        ("GET", "/console/feedback"),
    ],
)
def test_FB_F02_student_cannot_read_or_handle_teacher_queue(candidate, method, path):
    client, service, actor = candidate
    actor[0] = Identity("student", "a", frozenset({AI_USE}))
    result = client.open(path, method=method, base_url=ORIGIN, headers=HEADERS, json={})
    assert result.status_code == 403
    assert not service.mock_calls


def test_FB_F01_missing_write_header_stops_before_feedback(candidate):
    client, service, actor = candidate
    actor[0] = Identity("student", "a", frozenset({AI_USE}))
    result = client.put(
        FEEDBACK,
        base_url=ORIGIN,
        headers={"Origin": ORIGIN},
        json={"rating": "helpful", "expected_revision": 0},
    )
    assert result.status_code == 403 and not service.mock_calls
