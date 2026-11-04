from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app import create_app
from app.api.auth import COOKIE

ORIGIN = "https://campusclaw.test"
WRITE_HEADERS = {"Origin": ORIGIN, "X-CampusClaw-Request": "same-origin"}


@pytest.fixture
def candidate(settings):
    auth = Mock()
    auth.current.return_value = SimpleNamespace(
        id="fixture-account", class_id="fixture-class", role="teacher"
    )
    materials = Mock()
    client = create_app(
        replace(settings, public_origin=ORIGIN), auth=auth, materials=materials
    ).test_client()
    client.set_cookie(COOKIE, "fixture-session", domain="campusclaw.test")
    return client, auth, materials


class UnreadBody:
    def read(self, *_args):
        pytest.fail("被拒绝的请求读取了请求体")

    readinto = read
    readline = read


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/api/v1/auth/sessions"),
        ("POST", "/api/v1/materials"),
        ("DELETE", "/api/v1/auth/sessions/current"),
    ],
)
@pytest.mark.parametrize(
    "headers",
    [
        {**WRITE_HEADERS, "Origin": "https://external.test"},
        {**WRITE_HEADERS, "Origin": "https://other.campusclaw.test"},
        {"X-CampusClaw-Request": "same-origin"},
        {"Origin": ORIGIN},
    ],
)
def test_AUTH_F05_rejects_before_body(candidate, method, path, headers):
    client, auth, materials = candidate
    response = client.open(
        path,
        method=method,
        base_url=ORIGIN,
        headers={**headers, "Idempotency-Key": "fixture-key"},
        environ_overrides={
            "wsgi.input": UnreadBody(),
            "CONTENT_LENGTH": "18",
            "CONTENT_TYPE": "application/json",
        },
    )
    assert response.status_code == 403
    assert response.json["code"] == 1200 and response.json["data"] is None
    assert response.json["request_id"] == response.headers["X-Request-ID"]
    assert "Set-Cookie" not in response.headers
    auth.login.assert_not_called()
    auth.logout.assert_not_called()
    materials.create.assert_not_called()


def test_ACL_F02_student_multipart_does_not_reach_body_or_repository(candidate):
    client, auth, materials = candidate
    auth.current.return_value.role = "student"
    response = client.post(
        "/api/v1/materials",
        base_url=ORIGIN,
        headers={
            **WRITE_HEADERS,
            "Idempotency-Key": "fixture-key",
            "X-Role": "teacher",
        },
        environ_overrides={
            "wsgi.input": UnreadBody(),
            "CONTENT_LENGTH": "18",
            "CONTENT_TYPE": "multipart/form-data; boundary=fixture",
        },
    )
    assert response.status_code == 403 and response.json["code"] == 1200
    materials.create.assert_not_called()


@pytest.mark.parametrize(
    ("target", "allowed"),
    [
        ("https://external.test", "/materials"),
        ("//external.test", "/materials"),
        ("/unknown", "/materials"),
        ("/console", "/console"),
        (
            "/materials/00000000-0000-0000-0000-000000000001",
            "/materials/00000000-0000-0000-0000-000000000001",
        ),
    ],
)
def test_AUTH_F06_only_renders_allowlisted_destination(candidate, target, allowed):
    client, _, _ = candidate
    response = client.get("/login", base_url=ORIGIN, query_string={"next": target})
    assert response.status_code == 200
    assert f'const destination = "{allowed}";' in response.text
