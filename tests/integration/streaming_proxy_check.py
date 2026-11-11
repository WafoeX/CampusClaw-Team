"""任务2.0：真实NGINX TLS→现有Gunicorn线程配置→可控HTTP慢上游。"""

import http.client
import json
import os
import ssl
import statistics
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NGINX = "nginx:1.30.6-alpine@sha256:583b7f2fce1cdb8da5ad5c39ebd3c33b98b87d493190e548bdee1fa8c619c311"


def verify_streaming_proxy(compose, folder):
    password = os.urandom(24).hex()
    label_rows = [
        json.loads(row) for row in compose("ps", "--format", "json").splitlines()
    ]
    app_id = next(row["ID"] for row in label_rows if row["Service"] == "app")
    project = subprocess.check_output(
        [
            "docker",
            "inspect",
            "--format",
            '{{index .Config.Labels "com.docker.compose.project"}}',
            app_id,
        ],
        text=True,
    ).strip()
    gateway = project + "-streaming-proxy"
    folder.mkdir()
    (folder / "tls").mkdir()
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=localhost",
            "-addext",
            "subjectAltName=DNS:localhost",
            "-keyout",
            str(folder / "tls/localhost.key"),
            "-out",
            str(folder / "tls/localhost.crt"),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    (folder / "nginx.conf").write_text(
        (ROOT / "deploy/nginx.conf").read_text().replace("app:8080", "app:8081")
    )
    context = ssl.create_default_context(cafile=str(folder / "tls/localhost.crt"))
    worker_file = Path(__file__).with_name("streaming_probe_worker.py")
    compose(
        "exec",
        "-T",
        "app",
        "python",
        "-c",
        "from pathlib import Path; import sys; Path('/tmp/streaming_probe_worker.py').write_text(sys.argv[1])",
        worker_file.read_text(),
    )
    compose(
        "exec",
        "-T",
        "app",
        "python",
        "-c",
        "from pathlib import Path; import sys; Path('/tmp/session_proxy_worker.py').write_text(sys.argv[1])",
        Path(__file__).with_name("session_proxy_worker.py").read_text(),
    )
    streams, samples, first_times, total_times = [], [], [], []
    try:
        subprocess.run(
            [
                "docker",
                "run",
                "--detach",
                "--name",
                gateway,
                "--label",
                f"com.docker.compose.project={project}",
                "--network",
                project + "_default",
                "--publish",
                "127.0.0.1::8443",
                "--user",
                f"{os.getuid()}:{os.getgid()}",
                "--mount",
                f"type=bind,src={folder},dst=/etc/campusclaw,readonly",
                "--mount",
                f"type=bind,src={folder / 'nginx.conf'},dst=/etc/nginx/nginx.conf,readonly",
                "--tmpfs",
                "/tmp:rw,size=16m,mode=1777",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
                "--entrypoint",
                "nginx",
                NGINX,
                "-g",
                "daemon off;",
            ],
            check=True,
            capture_output=True,
            timeout=60,
        )
        port = int(
            subprocess.check_output(["docker", "port", gateway, "8443"], text=True)
            .strip()
            .rsplit(":", 1)[1]
        )
        origin = f"https://localhost:{port}"
        compose("up", "--build", "--wait", "--no-deps", "mcp-server")
        tool_address = compose(
            "exec",
            "-T",
            "app",
            "python",
            "-c",
            "import socket; print(socket.gethostbyname('mcp-server'))",
        )
        compose(
            "exec",
            "-d",
            "-e",
            "PYTHONPATH=/srv/campusclaw",
            "app",
            "python",
            "/tmp/streaming_probe_worker.py",
            "upstream",
        )
        compose(
            "exec",
            "-d",
            "-e",
            f"SSE_PROBE_ORIGIN={origin}",
            "-e",
            f"SSE_PROBE_PASSWORD={password}",
            "-e",
            f"MCP_SERVICE_NETWORK={tool_address}/32",
            "-e",
            "PYTHONPATH=/srv/campusclaw:/tmp",
            "app",
            "python",
            "-m",
            "gunicorn",
            "--config",
            "python:app.wsgi_config",
            "--bind",
            "0.0.0.0:8081",
            "--pid",
            "/tmp/streaming-probe-gunicorn.pid",
            "streaming_probe_worker:load_worker()",
        )

        def request(
            method,
            path,
            *,
            cookie=None,
            body=None,
            write_headers=True,
            key=None,
            header_overrides=None,
        ):
            connection = http.client.HTTPSConnection(
                "localhost", port, context=context, timeout=3
            )
            headers = {"Content-Type": "application/json"}
            if key:
                headers["Idempotency-Key"] = key
            if cookie:
                headers["Cookie"] = cookie
            if write_headers:
                headers.update(
                    {"Origin": origin, "X-CampusClaw-Request": "same-origin"}
                )
            headers.update(header_overrides or {})
            connection.request(
                method,
                path,
                body=json.dumps(body) if body is not None else None,
                headers=headers,
            )
            response = connection.getresponse()
            return connection, response

        def json_request(method, path, **kwargs):
            started = time.monotonic()
            connection, response = request(method, path, **kwargs)
            try:
                return (
                    response.status,
                    json.loads(response.read()),
                    (time.monotonic() - started) * 1000,
                    response.getheaders(),
                )
            finally:
                connection.close()

        def eventually(action):
            until = time.monotonic() + 10
            while time.monotonic() < until:
                try:
                    value = action()
                    if value:
                        return value
                except (OSError, ValueError, http.client.HTTPException):
                    pass
                time.sleep(0.05)
            raise AssertionError("流式夹具未在时限内达到预期")

        eventually(lambda: json_request("GET", "/health")[1].get("status") == "ready")
        cookies = []
        for index in range(20):
            status, body, _, headers = json_request(
                "POST",
                "/api/v1/auth/sessions",
                body={"login_name": f"sse_student_{index}", "password": password},
            )
            assert status == 200 and body["code"] == 0
            cookies.append(
                next(
                    value.split(";", 1)[0]
                    for key, value in headers
                    if key.lower() == "set-cookie"
                )
            )

        def metrics():
            return json_request("GET", "/__sse_probe_metrics", cookie=cookies[0])[1][
                "data"
            ]

        def upstream(path, *, method="GET"):
            result = compose(
                "exec",
                "-T",
                "app",
                "python",
                "-c",
                "import http.client,sys; c=http.client.HTTPConnection('127.0.0.1',9090,timeout=2); c.request(sys.argv[1],sys.argv[2]); r=c.getresponse(); print(r.read().decode() or '{}')",
                method,
                path,
            )
            return json.loads(result)

        def frame(response):
            lines = []
            while True:
                line = response.readline()
                assert line, "流在终态前断开"
                if line.startswith(b":"):
                    continue
                if line == b"\n":
                    if lines:
                        return lines[0].decode().strip().removeprefix(
                            "event: "
                        ), json.loads(lines[1].removeprefix(b"data: "))
                else:
                    lines.append(line)

        def open_stream(identifier, index=0):
            started = time.monotonic()
            connection, response = request(
                "POST", "/__sse_probe/" + identifier, cookie=cookies[index], body={}
            )
            streams.append((connection, response))
            assert response.status == 200 and response.getheader(
                "Content-Type"
            ).startswith("text/event-stream")
            assert response.getheader("Cache-Control") == "no-store"
            assert frame(response)[0] == "meta"
            event, payload = frame(response)
            assert event == "delta" and payload["data"]["text"] == "电压为24伏\n"
            return connection, response, started

        from tests.integration.session_proxy_check import verify_sessions
        from tests.integration.tool_proxy_check import verify_tools

        verify_tools(request, json_request, frame, cookies, compose, password)

        verify_sessions(
            request,
            json_request,
            frame,
            upstream,
            metrics,
            eventually,
            cookies,
            streams,
            compose,
            password,
        )

        # 匿名和缺写入头在SSE前拒绝，外部请求为零。
        assert json_request("POST", "/__sse_probe/anonymous", body={})[0] == 401
        assert (
            json_request(
                "POST",
                "/__sse_probe/missing-header",
                cookie=cookies[0],
                body={},
                write_headers=False,
            )[0]
            == 403
        )
        assert upstream("/metrics")["active"] == []
        for index in range(3):
            identifier = f"incremental-{index}"
            connection, response, started = open_stream(identifier)
            first = time.monotonic()
            state = upstream("/metrics")
            assert (
                identifier in state["active"] and identifier not in state["completed"]
            )
            first_times.append((first - started) * 1000)
            upstream("/release/" + identifier, method="POST")
            assert frame(response)[0] == "delta"
            event, payload = frame(response)
            assert (
                event == "done"
                and payload["data"]["text"] == "电压为24伏\n频率为50赫兹\n"
            )
            assert identifier in metrics()["committed"]
            assert response.read() == b""
            connection.close()
            total_times.append((time.monotonic() - started) * 1000)
        eventually(lambda: metrics()["active"] == 0)

        connection, response, _ = open_stream("cancel")
        # shutdown下游连接，下一次心跳触发Gunicorn close及上游socket取消。
        response.close()
        connection.close()
        eventually(lambda: "cancel" in upstream("/metrics")["cancelled"])
        eventually(lambda: metrics()["active"] == 0)
        assert (
            "cancel" not in metrics()["committed"] and "cancel" in metrics()["aborted"]
        )

        connection, response, _ = open_stream("invalid-second")
        upstream("/release/invalid-second", method="POST")
        event, payload = frame(response)
        assert event == "error" and payload["code"] == 1501
        assert response.read() == b"" and "invalid-second" not in metrics()["committed"]
        connection.close()
        eventually(lambda: metrics()["active"] == 0)

        for index in range(4):
            open_stream(f"saturated-{index}", index)
        assert metrics()["active"] == 4
        status, body, elapsed, _ = json_request(
            "POST", "/__sse_probe/over-limit", cookie=cookies[4], body={}
        )
        assert status == 429 and body["code"] == 1600 and elapsed <= 1000
        assert "over-limit" not in upstream("/metrics")["active"]

        # 同一1000条数据，10并发50样本；真实TLS/NGINX/当前WSGI与数据库。
        def ordinary(index):
            path = "/api/v1/materials"
            status, body, elapsed, _ = json_request("GET", path, cookie=cookies[4])
            assert status == 200, (
                path,
                status,
                body.get("code"),
                body.get("status"),
                elapsed,
            )
            if path == "/api/v1/materials":
                assert body["data"]["total"] == 1000
            assert elapsed <= 1000, (path, elapsed)
            return {"path": path, "duration_ms": round(elapsed, 2)}

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(ordinary, index) for index in range(50)]
            # 同时检查探针；逐次发起，不超过骨架每依赖两个探测槽的既有契约。
            for _ in range(5):
                for path in ("/live", "/health"):
                    probe_status, _, elapsed, _ = json_request("GET", path)
                    assert probe_status == 200 and elapsed <= 1000, (
                        path,
                        probe_status,
                        elapsed,
                    )
                    samples.append({"path": path, "duration_ms": round(elapsed, 2)})
            samples.extend(future.result() for future in futures)
        # 排空同时结束四个长流，探针仍可响应；取消回收后清除测试marker。
        compose(
            "exec",
            "-T",
            "app",
            "python",
            "-c",
            "from pathlib import Path; Path('/tmp/streaming-probe-draining').touch()",
        )
        assert json_request("GET", "/live")[0] == 200
        assert json_request("GET", "/health")[0] == 503
        for connection, response in streams[-4:]:
            event, payload = frame(response)
            assert event == "error" and payload["code"] == 1500
            assert response.read() == b""
            connection.close()
        compose(
            "exec",
            "-T",
            "app",
            "python",
            "-c",
            "from pathlib import Path; Path('/tmp/streaming-probe-draining').unlink()",
        )
        eventually(lambda: metrics()["active"] == 0)
        assert all(
            not value.startswith("saturated") for value in metrics()["committed"]
        )
        report = {
            "scope": "task-2.0-transport-only",
            "workers": 1,
            "threads": 8,
            "long_request_limit": 4,
            "materials": 1000,
            "short_request_concurrency": 10,
            "short_request_samples": samples,
            "first_segment_ms": first_times,
            "total_ms": total_times,
            "short_median_ms": statistics.median(row["duration_ms"] for row in samples),
            "short_p95_ms": sorted(row["duration_ms"] for row in samples)[
                int(len(samples) * 0.95) - 1
            ],
            "incremental_before_upstream_release": True,
            "upstream_cancelled": True,
            "drain_released": True,
        }
        output = ROOT / "reports/2026-11-04-add-streaming-ai-assistant/minimal-sse.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    finally:
        for connection, response in streams:
            response.close()
            connection.close()
        compose(
            "exec",
            "-T",
            "app",
            "python",
            "-c",
            "from pathlib import Path; import os,signal;\nfor name in ('gunicorn','upstream'):\n p=Path('/tmp/streaming-probe-'+name+'.pid')\n if p.exists():\n  try: os.kill(int(p.read_text()),signal.SIGTERM)\n  except ProcessLookupError: pass",
            check=False,
        )
        subprocess.run(
            ["docker", "rm", "--force", gateway],
            check=True,
            capture_output=True,
            timeout=30,
        )
