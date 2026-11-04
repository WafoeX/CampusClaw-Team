import json
import sys
from email.message import Message

import pytest

from scripts import verify_runtime as runtime

REVISION = "a" * 40


@pytest.fixture
def probes(monkeypatch):
    health = {
        "status": "ready",
        "version": REVISION,
        "time": "2026-11-04T04:00:00Z",
        "dependencies": {"mysql": "ready", "qdrant": "ready"},
        "request_id": "b" * 32,
    }
    live = {"status": "alive", "request_id": "c" * 32}
    options = {"head_body": b"", "cache": "no-store", "status": 200}

    def request(_port, path, method="GET"):
        body = health if path == "/health" else live
        headers = Message()
        headers["Content-Type"] = "application/json"
        headers["Cache-Control"] = options["cache"]
        headers["X-Request-ID"] = body["request_id"]
        raw = json.dumps(body).encode() if method == "GET" else options["head_body"]
        return options["status"], raw, headers

    monkeypatch.setattr(runtime, "request", request)
    return health, options


def test_RT_N01_RT_N02_RT_B03_record_checks_both_probes(probes):
    observed = runtime.inspect_probes(8000, REVISION)
    assert observed == {
        "/live": {"http_status": 200, "request_id": "c" * 32},
        "/health": {"http_status": 200, "request_id": "b" * 32},
    }


def test_RT_N01_record_rejects_wrong_version(probes):
    with pytest.raises(runtime.VerificationError, match="运行版本"):
        runtime.inspect_probes(8000, "d" * 40)


@pytest.mark.parametrize("status", ["degraded", "not_ready"])
def test_RT_F03_RT_B01_record_requires_both_dependencies(probes, status):
    health, _ = probes
    health["status"] = status
    health["dependencies"]["qdrant"] = "unavailable"
    with pytest.raises(runtime.VerificationError, match="两项依赖"):
        runtime.inspect_probes(8000, REVISION)


def test_RT_B03_record_rejects_head_body(probes):
    _, options = probes
    options["head_body"] = b"unexpected"
    with pytest.raises(runtime.VerificationError, match="HEAD"):
        runtime.inspect_probes(8000, REVISION)


def test_RT_B03_record_rejects_cached_response(probes):
    _, options = probes
    options["cache"] = "max-age=60"
    with pytest.raises(runtime.VerificationError, match="响应头"):
        runtime.inspect_probes(8000, REVISION)


def test_RT_N01_record_rejects_dirty_checkout(monkeypatch):
    def command(*args):
        return REVISION if args[1] == "rev-parse" else " M app/config.py"

    monkeypatch.setattr(runtime, "command", command)
    with pytest.raises(runtime.VerificationError, match="工作区"):
        runtime.collect(8000)


def test_RT_F05_record_does_not_copy_untrusted_fields(probes, monkeypatch):
    health, _ = probes
    health["unexpected"] = "private-sentinel"
    monkeypatch.setenv("MYSQL_PASSWORD", "private-sentinel")

    def command(*args):
        if args[:2] == ("git", "rev-parse"):
            return REVISION
        if args[:2] == ("git", "status"):
            return ""
        return "test-version"

    monkeypatch.setattr(runtime, "command", command)
    report = runtime.collect(8000)
    assert report["revision"] == REVISION and report["worktree_clean"] is True
    assert "private-sentinel" not in json.dumps(report)
    assert "待成员" in report["review"]


def test_CK_F02_record_does_not_overwrite_previous_evidence(tmp_path, monkeypatch):
    output = tmp_path / "record.json"
    output.write_text("previous evidence")
    monkeypatch.setattr(runtime, "collect", lambda _: {"result": "passed"})
    monkeypatch.setattr(sys, "argv", ["verify_runtime", "--output", str(output)])
    assert runtime.main() == 1
    assert output.read_text() == "previous evidence"


def test_CK_F03_failed_verification_does_not_write_success(tmp_path, monkeypatch):
    output = tmp_path / "record.json"

    def fail(_port):
        raise runtime.VerificationError("探针尚未就绪")

    monkeypatch.setattr(runtime, "collect", fail)
    monkeypatch.setattr(sys, "argv", ["verify_runtime", "--output", str(output)])
    assert runtime.main() == 1
    assert not output.exists()
