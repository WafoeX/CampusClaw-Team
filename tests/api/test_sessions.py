"""ST-F01/F02/F03：匿名、同源及消息输入白名单的公开HTTP契约。"""

import pytest

from app.services.access import Identity
from app.services.ai_contracts import AI_USE
from tests.api.test_ai_apps import HEADERS, ID, ORIGIN

pytest_plugins = ["tests.api.test_ai_apps"]


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/v1/sessions"),
        ("POST", "/api/v1/sessions"),
        ("GET", "/api/v1/sessions/" + ID),
        ("POST", "/api/v1/sessions/" + ID + "/messages"),
    ],
)
def test_ST_F02_anonymous_has_no_stream_or_writes(candidate, method, path):
    client, service, _ = candidate
    result = client.open(path, method=method, base_url=ORIGIN, headers=HEADERS, json={})
    assert result.status_code == 401 and result.json["code"] == 1100
    assert result.mimetype != "text/event-stream" and not service.mock_calls


def test_ST_F01_valid_session_wrong_origin_and_missing_key_fail_before_service(
    candidate,
):
    client, service, actor = candidate
    actor[0] = Identity("student", "a", frozenset({AI_USE}))
    for headers, status in [
        (HEADERS | {"Origin": "https://other.test"}, 403),
        ({k: v for k, v in HEADERS.items() if k != "Idempotency-Key"}, 400),
    ]:
        result = client.post(
            "/api/v1/sessions/" + ID + "/messages",
            base_url=ORIGIN,
            headers=headers,
            json={"question": "合成问题"},
        )
        assert result.status_code == status and result.mimetype != "text/event-stream"
        assert not service.mock_calls


def test_ST_F01_duplicate_keys_fail_before_acceptance(candidate):
    client, service, actor = candidate
    actor[0] = Identity("student", "a", frozenset({AI_USE}))
    result = client.post(
        "/api/v1/sessions/" + ID + "/messages",
        base_url=ORIGIN,
        headers=HEADERS,
        data='{"question":"问题一","question":"问题二"}',
        content_type="application/json",
    )
    assert result.status_code == 400 and not service.mock_calls
