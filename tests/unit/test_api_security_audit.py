import json
from types import SimpleNamespace

import pytest
from flask import Flask, Response, g

from app.api.auth import COOKIE
from app.services.ai_contracts import AI_CONFIGURE
from scripts.audit_api_security import TestEvidence as Evidence
from scripts.audit_api_security import build_report, inventory, observe


@pytest.fixture
def local_app():
    app = Flask("app", static_folder=None)
    app.add_url_rule("/api/v1/skills/<value>", "update_skill", methods=["PATCH"])
    app.add_url_rule("/api/v1/auth/sessions", "login", methods=["POST"])
    return app


def rows(app):
    return inventory(
        app,
        {("update_skill", "PATCH"): AI_CONFIGURE},
        {("login", "/api/v1/auth/sessions", "POST")},
    )


def test_configuration_policy_and_public_exception(local_app):
    key = "PATCH", "/api/v1/skills/<value>"
    local_app.add_url_rule("/api/v1/assistants", "new_config", methods=["POST"])
    local_app.add_url_rule("/api/v1/operation-audits", "audit", methods=["GET"])
    results = inventory(
        local_app,
        {("update_skill", "PATCH"): "session", ("audit", "GET"): "session"},
        {("login", "/api/v1/auth/sessions", "POST"), ("update_skill", key[1], key[0])},
    )
    assert len(results[key].findings) == 2
    assert results[("POST", "/api/v1/auth/sessions")].findings == set()
    assert results[("GET", "/api/v1/operation-audits")].findings == {
        "审计或连接器管理入口缺少教师配置权限登记"
    }
    assert any("CSRF" in f for f in results[("POST", "/api/v1/assistants")].findings)
    assert any(
        "缺少授权登记" in f for f in results[("POST", "/api/v1/assistants")].findings
    )


def test_response_evidence_is_scoped_and_redacted(local_app):
    results = rows(local_app)
    evidence = Evidence(results)
    with local_app.test_request_context("/api/v1/skills/private-id", method="PATCH"):
        response = Response("private-body", status=200)
        response.set_cookie(COOKIE, "private-cookie")
        evidence.capture(local_app, response)
        evidence.pytest_runtest_logreport(
            SimpleNamespace(failed=True, nodeid="test_api.py::test_config[private-id]")
        )
    report = build_report(results, 0)
    row = results[("PATCH", "/api/v1/skills/<value>")].row()
    assert len(row["findings"]) == 3 and row["statuses"] == [200]
    assert row["failed_tests"] == ["test_api.py::test_config"]
    assert report["flagged"] == 1 and report["exit_code"] == 1
    assert "private-" not in json.dumps(report)


def test_secure_response_and_unobserved_operation(local_app):
    results = rows(local_app)
    with local_app.test_request_context("/api/v1/skills/fixture", method="PATCH"):
        g.identity = object()
        response = Response(status=200, headers={"Cache-Control": "private, no-store"})
        response.set_cookie(
            COOKIE, "fixture", secure=True, httponly=True, samesite="Strict"
        )
        observe(results, local_app, response)
        observe(results, local_app, Response(status=403))
    report = build_report(results, 0)
    assert (
        report["exit_code"] == 0 and report["observed"] == 1 and report["flagged"] == 0
    )
    assert results[("PATCH", "/api/v1/skills/<value>")].statuses == {200, 403}
    assert results[("POST", "/api/v1/auth/sessions")].row()["coverage"] == "未观察"
    assert build_report(results, 1)["exit_code"] == 2


def test_no_observations_or_foreign_app_are_incomplete(local_app):
    results = rows(local_app)
    with local_app.test_request_context("/api/v1/skills/fixture", method="PATCH"):
        observe(results, Flask("another"), Response(status=200))
    assert build_report(results, 0)["exit_code"] == 2


def test_mcp_session_response_finding_and_secure_control():
    from scripts.audit_api_security import Operation

    service = Flask("teaching_server", static_folder=None)
    service.add_url_rule("/mcp", "endpoint", methods=["POST"])
    key = "POST", "/mcp"
    results = {key: Operation(*key, "endpoint")}
    response = Response(headers={"Mcp-Session-Id": "private-session"})
    with service.test_request_context(
        "/mcp", method="POST", headers={"Authorization": "Bearer fixture"}
    ):
        observe(results, service, response)
        assert results[key].findings == {
            "初始化响应含 MCP 会话标识，缺少 Cache-Control: no-store"
        }
        assert "private-session" not in json.dumps(build_report(results, 0))
        results[key].findings.clear()
        response.cache_control.no_store = True
        observe(results, service, response)
        assert not results[key].findings
    with service.test_request_context("/mcp", method="POST"):
        observe(results, service, response)
        assert any("Bearer" in finding for finding in results[key].findings)
