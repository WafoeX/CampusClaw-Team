import json
from datetime import timedelta

import pytest

from scripts.watch_skill_alerts import watch
from tests.unit.test_skill_alerts import SKILL, START, VERSION, row


def invoke(tmp_path, outcomes, *, recovery=False):
    source = tmp_path / "events.jsonl"
    lines = [row(second) for second in range(-285, 301, 15)]
    if recovery:
        lines.extend(row(second, "succeeded") for second in range(315, 661, 15))
    else:
        lines.extend(row(second) for second in range(315, 361, 15))
    source.write_text("\n".join(lines))
    now = [START + timedelta(seconds=631 if recovery else 301)]
    calls, reports = [], []

    def sender(events, **_configuration):
        calls.extend(events)
        return [
            {
                "event_id": event["event_id"],
                "state": event["state"],
                "status": next(outcomes),
            }
            for event in events
        ]

    result = watch(
        source,
        version=VERSION,
        skills=[SKILL],
        start=START,
        until=now[0] + timedelta(seconds=31),
        destination="https://receiver.test",
        panel="https://panel.test",
        token="synthetic",
        clock=lambda: now[0],
        sleep=lambda seconds: now.__setitem__(0, now[0] + timedelta(seconds=seconds)),
        sender=sender,
        emit=reports.append,
    )
    return result, calls, reports


def test_L10_N05_watcher_retries_same_event_and_stops_after_confirmation(tmp_path):
    code, calls, reports = invoke(tmp_path, iter(["failed", "delivered"]))
    assert code == 0 and len(calls) == 2 and len(reports) == 3
    assert calls[0] == calls[1]
    assert reports[-1]["deliveries"] == []
    assert "synthetic" not in json.dumps(reports)


def test_L10_F05_watcher_cannot_hide_unconfirmed_or_late_delivery(tmp_path):
    code, calls, reports = invoke(tmp_path, iter(["failed"] * 3))
    assert code == 1 and len(calls) == len(reports) == 3
    code, calls, reports = invoke(tmp_path, iter(["late"]))
    assert code == 1 and len(calls) == 1


def test_L10_F05_recovery_waits_for_failed_firing_delivery(tmp_path):
    code, calls, _ = invoke(
        tmp_path, iter(["failed", "delivered", "delivered"]), recovery=True
    )
    assert code == 0
    assert [event["state"] for event in calls] == ["firing", "firing", "resolved"]


def test_L10_F05_watcher_rejects_truncated_log(tmp_path):
    source = tmp_path / "events.jsonl"
    source.write_text(row(0))
    now = [START]

    def truncate(seconds):
        source.write_text("")
        now[0] += timedelta(seconds=seconds)

    with pytest.raises(ValueError, match="截短"):
        watch(
            source,
            version=VERSION,
            skills=[SKILL],
            start=START,
            until=START + timedelta(minutes=1),
            destination="https://receiver.test",
            panel="https://panel.test",
            token="synthetic",
            clock=lambda: now[0],
            sleep=truncate,
            sender=lambda *_args, **_kwargs: [],
            emit=lambda _record: None,
        )
