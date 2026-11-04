import json
from datetime import UTC, datetime
from threading import Event, Thread

import pytest


def test_RT_N02_anonymous_probe_contract(make_app):
    calls = []

    def mysql():
        calls.append("mysql")
        return True

    client = make_app(mysql=mysql).test_client()
    live = client.get("/live")
    assert live.status_code == 200
    assert live.json == {"status": "alive", "request_id": live.headers["X-Request-ID"]}
    assert calls == []
    health = client.get("/health")
    assert health.status_code == 200
    payload = health.json
    assert set(payload) == {"status", "version", "time", "dependencies", "request_id"}
    assert payload["status"] == "ready"
    assert payload["version"] == "test-build"
    assert (
        payload["time"].endswith("Z")
        and datetime.fromisoformat(payload["time"]).tzinfo == UTC
    )
    assert payload["dependencies"] == {"mysql": "ready", "qdrant": "ready"}
    assert payload["request_id"] == health.headers["X-Request-ID"]
    assert calls == ["mysql"]


def test_RT_F04_slow_core_keeps_liveness_available(make_app):
    started = Event()
    release = Event()
    calls = []
    responses = []

    def mysql():
        calls.append(1)
        started.set()
        return release.wait(3)

    app = make_app(mysql=mysql)
    worker = Thread(target=lambda: responses.append(app.test_client().get("/health")))
    worker.start()
    try:
        assert started.wait(1)
        assert app.test_client().get("/live").status_code == 200
        worker.join(2)
        assert not worker.is_alive()
        assert responses[0].status_code == 503
        assert responses[0].json["dependencies"]["mysql"] == "unavailable"
        assert calls == [1]
    finally:
        release.set()
        worker.join()


def test_RT_F03_RT_B01_aggregate_dependency_status_without_network(make_app):
    available = {"mysql": True, "qdrant": True}
    client = make_app(
        mysql=lambda: available["mysql"], qdrant=lambda: available["qdrant"]
    ).test_client()
    available["qdrant"] = False
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json["status"] == "degraded"
    assert response.json["dependencies"] == {"mysql": "ready", "qdrant": "unavailable"}
    available.update(mysql=False, qdrant=True)
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json["status"] == "not_ready"
    assert response.json["dependencies"] == {"mysql": "unavailable", "qdrant": "ready"}
    assert client.get("/live").status_code == 200
    available["mysql"] = True
    assert client.get("/health").json["status"] == "ready"


@pytest.mark.parametrize("core_ready", [True, False])
def test_RT_B03_head_retains_status_and_headers_without_body(make_app, core_ready):
    client = make_app(mysql=lambda: core_ready).test_client()
    for path in ("/health", "/live"):
        head, get = client.head(path), client.get(path)
        assert (
            head.status_code
            == get.status_code
            == (200 if path == "/live" or core_ready else 503)
        )
        assert head.mimetype == get.mimetype == "application/json"
        assert (
            head.headers["Cache-Control"] == get.headers["Cache-Control"] == "no-store"
        )
        assert head.headers["X-Request-ID"] != get.headers["X-Request-ID"]
        assert not head.data


def test_RT_N03_RT_F05_json_logs_use_server_request_ids_and_redact(make_app, capsys):
    def mysql():
        raise OSError("mysql.private.example synthetic-db-value")

    client = make_app(mysql=mysql).test_client()
    health = client.get(
        "/health?value=unsafe%0Anew-line",
        headers={"X-Request-ID": "forged", "Authorization": "Bearer synthetic-token"},
    )
    denied = client.get("/missing")
    captured = capsys.readouterr().out
    rows = [json.loads(line) for line in captured.splitlines()]
    assert [row["request_id"] for row in rows] == [
        health.headers["X-Request-ID"],
        denied.headers["X-Request-ID"],
    ]
    assert len({row["request_id"] for row in rows}) == 2
    assert all(
        row["version"] == "test-build" and row["module"] == "http" for row in rows
    )
    assert all({"ts", "level", "duration_ms"} <= row.keys() for row in rows)
    observed = captured + health.get_data(as_text=True)
    for sentinel in (
        "unsafe",
        "new-line",
        "forged",
        "synthetic-token",
        "mysql.private",
        "synthetic-db-value",
    ):
        assert sentinel not in observed
