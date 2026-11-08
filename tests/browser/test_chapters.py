"""章节浏览器主路径：显式执行，需 Node 22+、Chromium、OpenSSL 和 Docker。"""

import http.client
import os
import ssl
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from uuid import uuid4

from tests.integration.test_compose import stack as compose_stack

stack = compose_stack


def test_CH_N01_CH_B01_browser_keyboard_and_two_widths(stack, tmp_path):
    compose, _, status, _ = stack
    assert status("ready")[0] == 200
    password = uuid4().hex
    compose("exec", "-T", "app", "python", "-m", "app.auth_admin", "upgrade")
    compose(
        "exec",
        "-T",
        "-e",
        "CAMPUSCLAW_ISOLATED_DATABASE=1",
        "-e",
        f"CAMPUSCLAW_SEED_PASSWORD={password}",
        "app",
        "python",
        "-m",
        "app.auth_admin",
        "seed",
    )
    backend = [None]

    class Proxy(BaseHTTPRequestHandler):
        def forward(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            upstream = http.client.HTTPConnection("127.0.0.1", backend[0], timeout=40)
            try:
                upstream.request(
                    self.command,
                    self.path,
                    body,
                    {**dict(self.headers), "Connection": "close"},
                )
                response = upstream.getresponse()
                data = response.read()
                self.send_response(response.status)
                for key, value in response.getheaders():
                    if key.lower() not in {
                        "connection",
                        "transfer-encoding",
                        "content-length",
                    }:
                        self.send_header(key, value)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            finally:
                upstream.close()

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = forward

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Proxy)
    certificate, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key),
            "-out",
            str(certificate),
            "-days",
            "1",
            "-subj",
            "/CN=localhost",
        ],
        check=True,
        capture_output=True,
        timeout=20,
    )
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(certificate, key)
    server.socket = tls.wrap_socket(server.socket, server_side=True)
    origin = f"https://127.0.0.1:{server.server_port}"
    worker = None
    try:
        container = compose(
            "run",
            "--rm",
            "-d",
            "--no-deps",
            "-p",
            "127.0.0.1::8080",
            "-e",
            f"APP_PUBLIC_ORIGIN={origin}",
            "-e",
            "EMBEDDING_BASE_URL=https://ai-gateway.devops.hello1023.com/v1",
            "-e",
            "EMBEDDING_MODEL=course-embedding",
            "-e",
            "EMBEDDING_DIM=2048",
            "-e",
            "RETRIEVAL_MIN_SCORE=0.449357",
            "-e",
            "PYTHONPATH=/srv/campusclaw:/tmp",
            "app",
            "python",
            "-c",
            "from pathlib import Path; import os,sys; Path('/tmp/ai_app_worker.py').write_text(sys.argv[1]); os.execvp('python',['python','-m','gunicorn','--config','python:app.wsgi_config','--bind','0.0.0.0:8080','ai_app_worker:load_worker()'])",
            Path(__file__).with_name("ai_app_worker.py").read_text(),
        ).splitlines()[-1]
        backend[0] = int(
            subprocess.check_output(
                ["docker", "port", container, "8080"],
                text=True,
                timeout=15,
            )
            .strip()
            .rsplit(":", 1)[1]
        )
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        chromium = os.environ["CAMPUSCLAW_CHROMIUM"]
        profile = tmp_path / "chrome"
        worker = subprocess.Popen(
            [
                chromium,
                "--headless=new",
                "--no-sandbox",
                "--ignore-certificate-errors",
                "--remote-debugging-port=0",
                f"--user-data-dir={profile}",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        output = Path("reports/2026-11-04-add-traceable-retrieval/browser").resolve()
        output.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "node",
                str(Path(__file__).with_name("chapters.mjs")),
                str(profile),
                origin,
                str(output),
            ],
            env={**os.environ, "CAMPUS_BROWSER_PASSWORD": password},
            check=True,
            timeout=120,
        )
    finally:
        if worker:
            worker.terminate()
            worker.wait(timeout=15)
        if backend[0] is not None:
            server.shutdown()
        server.server_close()
