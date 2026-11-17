import json
from datetime import timedelta
from io import StringIO
from uuid import UUID

import pytest

from scripts.observability_dashboard import main, render, summarize, utc

VERSION = "a" * 40
SKILLS = [str(UUID(int=index)) for index in (1, 2, 3)]
START = utc("2026-11-18T08:00:00+08:00")
END = START + timedelta(minutes=11)


def event(module, minute, **fields):
    return {
        "version": VERSION,
        "module": module,
        "ts": (START + timedelta(minutes=minute)).isoformat(),
    } | fields


def skill_event(skill, status, minute):
    return event(
        "skill_execution",
        12,  # 采集延迟跨窗时，仍按审计完成时间归属。
        skill_id=skill,
        status=status,
        completed_at=(START + timedelta(minutes=minute)).isoformat(),
        request_id="private-correlation-marker",
    )


def test_L10_N05_observed_metrics_use_candidate_window_and_finite_samples():
    rows = [
        skill_event(SKILLS[0], "succeeded", 0),
        skill_event(SKILLS[0], "failed", 2),
        skill_event(SKILLS[0], "interrupted", 3),
        skill_event(SKILLS[1], "succeeded", 1),
        skill_event(SKILLS[2], "succeeded", 5),
        skill_event(SKILLS[2], "failed", 11),
        skill_event(SKILLS[1], "failed", 1) | {"version": "b" * 40},
        skill_event(SKILLS[1], "unknown", 1),
        event("http", 2, duration_ms=9000),
        event("http", 2, route="/api/v1/quizzes", duration_ms=float("inf")),
        event("http", 2, route="/api/v1/quizzes", duration_ms=True),
        event("http", 2, route="/api/v1/quizzes", duration_ms=-1),
        event("teaching_backlog", 4, states={"pending": 3, "running": 10}),
        event("teaching_backlog", 1, states={"pending": 17}),
        event("teaching_backlog", 5, states={"running": 10}),
        event("teaching_backlog", 10, states={"pending": -2}),
    ] + [
        event("http", 1, route="/api/v1/quizzes/<value>", duration_ms=duration)
        for duration in range(1, 21)
    ]
    result = summarize(
        [*map(json.dumps, rows), "not JSON", "[]"],
        version=VERSION,
        skills=SKILLS,
        start=START,
        end=END,
    )
    first, second, third = result["windows"]
    assert first["start"] == "2026-11-18T00:00:00Z"
    assert [item["calls"] for item in first["skills"].values()] == [3, 1, 0]
    assert first["skills"][SKILLS[0]] == {
        "calls": 3,
        "failed": 1,
        "interrupted": 1,
        "error_percent": pytest.approx(100 / 3),
    }
    assert [item["error_percent"] for item in first["skills"].values()][1:] == [0, None]
    assert second["skills"][SKILLS[2]]["calls"] == 1
    assert [bucket["api_p95_ms"] for bucket in result["windows"]] == [19, None, None]
    assert first["api_samples"] == 20
    assert [bucket["pending"] for bucket in result["windows"]] == [3, 0, None]
    assert all(item["error_percent"] is None for item in third["skills"].values())
    html = render(result)
    assert "private-correlation-marker" not in html and "/api/v1/quizzes" not in html
    assert '"api_p95_ms": 19' in html
    assert html.count("<canvas ") == 4


def test_L10_N05_cli_supports_empty_stream_and_reports_parameter_error(
    monkeypatch, capsys
):
    monkeypatch.setattr("sys.stdin", StringIO(""))
    args = [
        "--version",
        VERSION,
        "--skill",
        SKILLS[0],
        "--start",
        START.isoformat(),
        "--end",
        END.isoformat(),
    ]
    main(args)
    captured = capsys.readouterr()
    assert '"api_p95_ms": null' in captured.out
    assert '"pending": null' in captured.out
    with pytest.raises(SystemExit) as error:
        main([*args, "--skill", SKILLS[0]])
    assert error.value.code == 2
    assert "互不重复" in capsys.readouterr().err
