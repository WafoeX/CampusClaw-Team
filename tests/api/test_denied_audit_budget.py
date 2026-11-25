"""DAB 拒绝审计预算的实际 HTTP 与事务边界回归。"""

from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
from flask import g

from app import create_app
from app.adapters.database import DatabaseError
from app.services.access import Identity
from app.services.ai_contracts import AI_USE

ORIGIN = "https://campusclaw.test"
HEADERS = {"Origin": ORIGIN, "X-CampusClaw-Request": "same-origin"}


def make_client(settings, **overrides):
    repository = MagicMock()
    ai = Mock(repository=repository, database_error=DatabaseError)
    ai.clock.return_value = datetime(2026, 11, 25)
    actor = SimpleNamespace(id="student-a", class_id="class-a", role="student")

    def identity():
        g.actor = actor
        return Identity(actor.id, actor.class_id, frozenset({"session", AI_USE}))

    app = create_app(
        replace(settings, public_origin=ORIGIN, **overrides),
        health=Mock(),
        auth=Mock(),
        materials=Mock(),
        chapters=Mock(),
        limiter=Mock(),
        indexing=Mock(),
        retrieval=Mock(),
        answers=Mock(),
        ai_apps=ai,
        teaching=Mock(),
        candidate_jobs=Mock(),
        tool_connectors=Mock(),
        resolve_identity=identity,
    )
    return app.test_client(), repository, actor


def reject(client, value="00000000-0000-0000-0000-000000000001", headers=HEADERS):
    response = client.patch(
        f"/api/v1/skills/{value}",
        base_url=ORIGIN,
        headers=headers,
        json={"name": "unauthorized-change", "revision": 1},
    )
    assert response.status_code == 403 and response.json["code"] == 1200
    assert response.json["data"] is None
    return response


def test_DAB_N01_default_budget_caps_real_rejected_http_writes(settings):
    client, repository, _ = make_client(settings)
    responses = [reject(client) for _ in range(65)]
    assert len({r.headers["X-Request-ID"] for r in responses}) == 65
    assert repository.append_operation_audit.call_count == 60
    assert repository.transaction.call_count == 60
    assert {
        call.args[1]["outcome"]
        for call in repository.append_operation_audit.call_args_list
    } == {"denied"}
