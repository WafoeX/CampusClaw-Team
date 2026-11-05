from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app import create_app
from app.api.auth import COOKIE
from app.services.access import AccessDenied
from app.services.rate_limits import RequestLimiter

ORIGIN = "https://campusclaw.test"
HEADERS = {"Origin": ORIGIN, "X-CampusClaw-Request": "same-origin"}


@pytest.fixture
def limited(settings):
    repository = Mock()
    repository.consume.return_value = (True, 20)
    auth = Mock()
    auth.current.return_value = SimpleNamespace(
        id="teacher-a",
        class_id="class-a",
        role="teacher",
        login_name="teacher",
        class_name="A",
        expires_at=datetime(2030, 1, 1),
    )
    auth.login.side_effect = AccessDenied(401, 1101, "账号或口令不正确")
    materials = Mock()
    app = create_app(
        replace(settings, public_origin=ORIGIN),
        auth=auth,
        materials=materials,
        limiter=RequestLimiter(repository, OSError),
    )
    client = app.test_client()
    client.set_cookie(COOKIE, "fixture", domain="campusclaw.test")
    return app, client, repository, auth, materials


def login(client, **options):
    return client.post(
        "/api/v1/auth/sessions",
        base_url=ORIGIN,
        headers={**HEADERS, **options},
        json={"login_name": "teacher", "password": "synthetic"},
    )


def test_RL_N01_login_and_write_use_separate_scopes(limited):
    _, client, repo, auth, _ = limited
    assert login(client).status_code == 401
    source = repo.consume.call_args.args[0]
    assert (
        client.delete(
            "/api/v1/auth/sessions/current", base_url=ORIGIN, headers=HEADERS
        ).status_code
        == 200
    )
    subject = repo.consume.call_args.args[0]
    assert source != subject
    before = repo.consume.call_count
    assert (
        client.get("/api/v1/auth/sessions/current", base_url=ORIGIN).status_code == 200
    )
    assert client.get("/live", base_url=ORIGIN).status_code == 200
    assert repo.consume.call_count == before
    auth.logout.assert_called_once()


@pytest.mark.parametrize("endpoint", ("login", "write"))
def test_RL_F04_rejection_has_retry_and_no_business_calls(limited, endpoint):
    _, client, repo, auth, materials = limited
    repo.consume.return_value = (False, 20)
    response = (
        login(client)
        if endpoint == "login"
        else client.post(
            "/api/v1/materials",
            base_url=ORIGIN,
            headers={**HEADERS, "Idempotency-Key": "synthetic"},
            json={"title": "title", "text": "text"},
        )
    )
    assert response.status_code == 429
    assert response.json["code"] == 1600 and response.json["data"] is None
    assert response.headers["Retry-After"] == "20"
    assert "Set-Cookie" not in response.headers
    auth.login.assert_not_called()
    materials.create.assert_not_called()


def test_RL_F01_denied_identity_or_origin_does_not_consume(limited):
    _, client, repo, auth, _ = limited
    assert login(client, Origin="https://untrusted.test").status_code == 403
    auth.current.return_value = None
    assert (
        client.delete(
            "/api/v1/auth/sessions/current", base_url=ORIGIN, headers=HEADERS
        ).status_code
        == 401
    )
    auth.current.return_value = SimpleNamespace(
        id="student-a", class_id="class-a", role="student"
    )
    assert (
        client.post("/api/v1/materials", base_url=ORIGIN, headers=HEADERS).status_code
        == 403
    )
    repo.consume.assert_not_called()


def test_RL_F03_dependency_failure_closes_before_auth(limited):
    _, client, repo, auth, _ = limited
    repo.consume.side_effect = OSError("synthetic")
    response = login(client)
    assert response.status_code == 503 and response.json["code"] == 1500
    auth.login.assert_not_called()


def test_RL_B01_forwarded_header_does_not_change_source(limited):
    app, client, repo, _, _ = limited
    login(client)
    original = repo.consume.call_args
    login(client, **{"X-Forwarded-For": "203.0.113.22"})
    assert repo.consume.call_args == original
    with app.test_client() as other:
        other.post(
            "/api/v1/auth/sessions",
            base_url=ORIGIN,
            headers=HEADERS,
            json={"login_name": "teacher", "password": "synthetic"},
            environ_overrides={"REMOTE_ADDR": "203.0.113.22"},
        )
    assert repo.consume.call_args != original
