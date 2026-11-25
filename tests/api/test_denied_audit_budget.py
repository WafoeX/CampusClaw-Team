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


def test_DAB_B01_http_caps_across_subjects_and_logs_once(settings, capsys):
    import json

    client, repository, actor = make_client(
        settings, audit_denied_subject_limit=2, audit_denied_global_limit=3
    )
    for _ in range(5):
        reject(client)
    actor.id = "student-b"
    for _ in range(4):
        reject(client)
    assert repository.transaction.call_count == 3
    records = [
        call.args[1] for call in repository.append_operation_audit.call_args_list
    ]
    assert [row["actor_id"] for row in records] == [
        "student-a",
        "student-a",
        "student-b",
    ]
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    budget_events = [
        event for event in events if event.get("event") == "denied_budget_exhausted"
    ]
    assert len(budget_events) == 1
    assert not {"actor_id", "class_id", "body", "cookie"} & budget_events[0].keys()
    assert (
        len(
            [
                event
                for event in events
                if event["module"] == "http" and event["status"] == 403
            ]
        )
        == 9
    )


@pytest.mark.parametrize("failure", ["enter", "append"])
def test_DAB_F03_store_failure_consumes_budget_and_preserves_denial(settings, failure):
    client, repository, _ = make_client(
        settings, audit_denied_subject_limit=2, audit_denied_global_limit=3
    )
    target = (
        repository.transaction.return_value.__enter__
        if failure == "enter"
        else repository.append_operation_audit
    )
    target.side_effect = DatabaseError("synthetic-store-unavailable")
    for _ in range(5):
        reject(client)
    assert repository.transaction.call_count == 2
    assert repository.append_operation_audit.call_count == (
        0 if failure == "enter" else 2
    )


def test_DAB_F02_missing_and_cross_class_targets_never_reach_configuration(settings):
    client, repository, _ = make_client(
        settings, audit_denied_subject_limit=1, audit_denied_global_limit=1
    )
    for value in (
        "00000000-0000-0000-0000-000000000001",
        "00000000-0000-0000-0000-000000000002",
        "00000000-0000-0000-0000-000000000099",
    ):
        reject(client, value)
    assert repository.transaction.call_count == 1
    assert {call[0] for call in repository.method_calls} <= {
        "transaction",
        "append_operation_audit",
    }


def test_DAB_F04_untrusted_origin_and_reads_do_not_consume_budget(settings):
    client, repository, _ = make_client(
        settings, audit_denied_subject_limit=1, audit_denied_global_limit=1
    )
    for headers in ({}, HEADERS | {"Origin": "https://other.invalid"}):
        reject(client, headers=headers)
    response = client.get("/api/v1/operation-audits", base_url=ORIGIN)
    assert response.status_code == 403
    assert repository.transaction.call_count == 0
    reject(client)
    assert repository.transaction.call_count == 1
