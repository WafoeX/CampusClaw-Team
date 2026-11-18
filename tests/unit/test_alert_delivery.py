import json
from datetime import timedelta
from unittest.mock import Mock

import pytest

from scripts.deliver_skill_alerts import deliver, https_url, notifications
from scripts.observability_dashboard import utc

AT = "2026-11-18T00:05:00Z"
NOW = utc(AT)
DESTINATION = "https://receiver.test/alerts"
SKILL = "00000000-0000-0000-0000-000000000001"


def report():
    return {
        "version": "a" * 40,
        "transitions": [
            {"skill_id": SKILL, "at": AT, "state": "firing"},
            {"skill_id": SKILL, "at": AT, "state": "no_data"},
            {"skill_id": SKILL, "at": AT, "state": "normal"},
        ],
    }


def test_L10_N05_delivery_is_idempotent_and_recovery_waits_for_normal():
    events = notifications(report(), "https://panel.test/dashboard")
    assert [event["state"] for event in events] == ["firing", "resolved"]
    assert (
        notifications(report(), "https://panel.test/changed")[0]["event_id"]
        == events[0]["event_id"]
    )
    received = {}

    def factory(host, port, timeout):
        assert host == "receiver.test"
        connection = Mock()

        def request(method, path, body, headers):
            payload = json.loads(body)
            assert method == "POST" and path == "/alerts"
            assert headers["Authorization"] == "Bearer synthetic"
            assert headers["Idempotency-Key"] == payload["event_id"]
            received.setdefault(payload["event_id"], payload)
            connection.getresponse.return_value = Mock(
                status=200,
                read=lambda limit: json.dumps(
                    {
                        "event_id": payload["event_id"],
                        "delivered": True,
                        "received_at": AT,
                    }
                ).encode()[:limit],
            )

        connection.request.side_effect = request
        return connection

    for _ in range(2):
        result = deliver(
            events,
            destination=DESTINATION,
            token="synthetic",
            connection_factory=factory,
            clock=lambda: NOW + timedelta(seconds=180),
        )
        assert [item["status"] for item in result] == ["delivered", "delivered"]
    assert len(received) == 2


@pytest.mark.parametrize(
    "mode", ["redirect", "missing", "wrong", "timeout", "large", "late"]
)
def test_L10_F05_no_valid_receipt_or_late_receipt_cannot_pass(mode):
    event = notifications(report(), "https://panel.test/dashboard")[0]

    def factory(*args, **kwargs):
        connection = Mock()
        if mode == "timeout":
            connection.request.side_effect = TimeoutError("synthetic")
        body = (
            b"x" * 8193
            if mode == "large"
            else json.dumps(
                {
                    "event_id": "wrong" if mode == "wrong" else event["event_id"],
                    "delivered": mode != "missing",
                    "received_at": (NOW + timedelta(seconds=121)).isoformat()
                    if mode == "late"
                    else AT,
                }
            ).encode()
        )
        connection.getresponse.return_value = Mock(
            status=302 if mode == "redirect" else 200,
            read=lambda limit: body[:limit],
        )
        return connection

    result = deliver(
        [event],
        destination=DESTINATION,
        token="synthetic",
        connection_factory=factory,
        clock=lambda: NOW + timedelta(seconds=121 if mode == "late" else 0),
    )
    assert result[0]["status"] == ("late" if mode == "late" else "failed")
    assert "synthetic" not in json.dumps(result)


@pytest.mark.parametrize(
    "url",
    [
        None,
        "http://receiver.test",
        "https://user:pass@receiver.test",
        "https://receiver.test/?key=x",
    ],
)
def test_L10_F05_destination_configuration_rejects_unsafe_values(url):
    with pytest.raises(ValueError):
        https_url(url)
