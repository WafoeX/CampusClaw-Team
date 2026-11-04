import json
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest


@pytest.fixture
def packaged_app(tmp_path):
    source = Path(__file__).resolve().parents[1] / "app"
    package = tmp_path / "app"
    shutil.copytree(source, package, ignore=shutil.ignore_patterns("__pycache__"))
    (package / "BUILD_VERSION").write_text("test-build")
    return tmp_path


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("MYSQL_PASSWORD", ""),
        ("MYSQL_PORT", "65536"),
        ("QDRANT_URL", "file:///internal"),
    ],
)
def test_RT_F01_RT_F02_process_exits_before_binding(
    packaged_app, config_env, key, value
):
    result = subprocess.run(
        [sys.executable, "-m", "app"],
        cwd=packaged_app,
        env={**config_env, key: value},
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 1
    assert not result.stderr
    row = json.loads(result.stdout)
    assert row["invalid_key"] == key
    assert row["request_id"] is None
    assert row["level"] == "ERROR"
    if value:
        assert value not in result.stdout


@pytest.fixture
def stalled_mysql():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        listener.settimeout(3)
        yield listener


def test_RT_B04_local_wsgi_process_reaches_probes_and_drains(
    packaged_app, config_env, stalled_mysql
):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    env = {
        **config_env,
        "MYSQL_HOST": "127.0.0.1",
        "MYSQL_PORT": str(stalled_mysql.getsockname()[1]),
        "QDRANT_URL": "http://127.0.0.1:1",
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "app", "--bind", f"127.0.0.1:{port}"],
        cwd=packaged_app,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    def request(path):
        try:
            response = urllib.request.urlopen(
                f"http://127.0.0.1:{port}{path}", timeout=2
            )
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    try:
        for _ in range(40):
            try:
                code, live = request("/live")
            except OSError:
                if proc.poll() is not None:
                    pytest.fail(f"WSGI 提前退出，退出码 {proc.returncode}")
                time.sleep(0.1)
            else:
                assert code == 200 and live["status"] == "alive"
                break
        else:
            pytest.fail("WSGI 进程未监听")
        with ThreadPoolExecutor(max_workers=1) as pool:
            inflight = pool.submit(request, "/health")
            connection, _ = stalled_mysql.accept()
            with connection:
                proc.send_signal(signal.SIGTERM)
                code, health = inflight.result(timeout=3)
                assert code == 503 and health["version"] == "test-build"
        stdout, stderr = proc.communicate(timeout=30)
        assert proc.returncode == 0 and not stderr
        rows = [json.loads(line) for line in stdout.splitlines()]
        assert [row.get("event") for row in rows if row["module"] != "http"] == [
            "starting",
            "draining",
            "stopped",
        ]
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.communicate(timeout=30)
