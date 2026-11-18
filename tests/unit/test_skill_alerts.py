import json
from datetime import timedelta
from io import StringIO

import pytest

from scripts.evaluate_skill_alerts import evaluate, main
from scripts.observability_dashboard import utc

VERSION = "a" * 40
SKILL = "00000000-0000-0000-0000-000000000001"
START = utc("2026-11-18T00:00:00Z")


def row(seconds, status="failed"):
    return json.dumps(
        {
            "module": "skill_execution",
            "version": VERSION,
            "skill_id": SKILL,
            "status": status,
            "completed_at": (START + timedelta(seconds=seconds)).isoformat(),
            "request_id": "private-marker",
        }
    )


def run(rows, end=901):
    return evaluate(
        rows,
        version=VERSION,
        skills=[SKILL],
        start=START,
        end=START + timedelta(seconds=end),
    )


def test_L10_N05_sustained_failures_fire_and_recovery_is_distinct_from_missing_data():
    rows = [row(second) for second in range(-285, 315, 15)]
    rows += [row(second, "succeeded") for second in range(315, 930, 15)]
    result = run(reversed(rows))
    assert [(item["at"], item["state"]) for item in result["transitions"]] == [
        ("2026-11-18T00:00:00Z", "pending"),
        ("2026-11-18T00:05:00Z", "firing"),
        ("2026-11-18T00:10:00Z", "normal"),
    ]
    assert result["states"][SKILL] == "normal"
    assert "private-marker" not in json.dumps(result)


def test_L10_F05_insufficient_samples_reset_hold_and_require_fresh_five_minutes():
    rows = [row(second) for second in range(-285, 0, 15)]
    rows += [row(second) for second in range(300, 901, 15)]
    result = run(rows)
    assert [(item["at"], item["state"]) for item in result["transitions"]] == [
        ("2026-11-18T00:09:45Z", "pending"),
        ("2026-11-18T00:14:45Z", "firing"),
    ]
    assert result["transitions"][-1]["notification"] == "required"


def test_L10_N05_one_percent_is_normal_and_wrong_candidate_cannot_count():
    rows = [row(0)] + [row(0, "succeeded")] * 99
    rows += [row(0).replace(VERSION, "b" * 40), "invalid", "[]"]
    result = run(rows, end=301)
    assert [item["state"] for item in result["transitions"]] == ["normal", "no_data"]
    assert result["transitions"][0]["error_percent"] == 1
    assert run([], end=301)["states"][SKILL] == "no_data"


def test_L10_F05_cli_rejects_duplicate_skills():
    with pytest.raises(SystemExit) as error:
        main(
            [
                "--version",
                VERSION,
                "--skill",
                SKILL,
                "--skill",
                SKILL,
                "--start",
                START.isoformat(),
                "--end",
                (START + timedelta(minutes=1)).isoformat(),
            ]
        )
    assert error.value.code == 2


def test_L10_N05_cli_emits_parseable_transitions(monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.stdin", StringIO("\n".join(row(second) for second in range(-285, 315, 15)))
    )
    main(
        [
            "--version",
            VERSION,
            "--skill",
            SKILL,
            "--start",
            START.isoformat(),
            "--end",
            (START + timedelta(seconds=301)).isoformat(),
        ]
    )
    result = json.loads(capsys.readouterr().out)
    assert result["states"] == {SKILL: "firing"}
    assert result["transitions"][-1]["at"] == "2026-11-18T00:05:00Z"
