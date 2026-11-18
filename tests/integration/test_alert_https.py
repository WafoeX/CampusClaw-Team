"""实际 TLS 收件端及命令行验证，证书和口令只存在于临时夹具。"""

import json
import os
import ssl
import subprocess
import sys
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from scripts.evaluate_skill_alerts import evaluate

ROOT = Path(__file__).resolve().parents[2]
SKILL = "00000000-0000-0000-0000-000000000001"
VERSION = "a" * 40


def certificate(folder, name):
    key, cert = folder / f"{name}.key", folder / f"{name}.crt"
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
            str(key),
            "-out",
            str(cert),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    key.chmod(0o600)
    return key, cert


def test_L10_N05_L10_F05_https_cli_requires_trust_hostname_and_matching_receipt(
    tmp_path,
):
    key, cert = certificate(tmp_path, "receiver")
    _, unrelated = certificate(tmp_path, "unrelated")
    now = datetime.now(UTC)
    start = now - timedelta(minutes=5)
    logs = [
        json.dumps(
            {
                "module": "skill_execution",
                "version": VERSION,
                "skill_id": SKILL,
                "status": "failed",
                "completed_at": (start + timedelta(seconds=second)).isoformat(),
            }
        )
        for second in range(-285, 301, 15)
    ]
    report = evaluate(
        logs,
        version=VERSION,
        skills=[SKILL],
        start=start,
        end=now + timedelta(microseconds=1),
    )
    assert report["states"] == {SKILL: "firing"}
    report["transitions"].append(
        {
            "skill_id": SKILL,
            "state": "normal",
            "at": (now + timedelta(microseconds=2)).isoformat(),
        }
    )
    received = {}
    failures = [True]
    requests = []

    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(payload)
            if failures[0]:
                self.send_response(503)
                self.end_headers()
                return
            if self.headers["Authorization"] != "Bearer synthetic-https":
                self.send_response(401)
                self.end_headers()
                return
            identifier = self.headers["Idempotency-Key"]
            assert identifier == payload["event_id"]
            assert payload["panel"] == "https://panel.test/dashboard"
            receipt = received.setdefault(
                identifier,
                {
                    "event_id": identifier,
                    "delivered": True,
                    "received_at": datetime.now(UTC).isoformat(),
                },
            )
            body = json.dumps(receipt).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    with ThreadingHTTPServer(("127.0.0.1", 0), Receiver) as server:
        server.socket = context.wrap_socket(server.socket, server_side=True)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()

        def command(
            host="localhost",
            trust=cert,
            token="synthetic-https",
            module="scripts.deliver_skill_alerts",
            extra=(),
        ):
            result = subprocess.run(
                [sys.executable, "-m", module, *extra],
                cwd=ROOT,
                input=json.dumps(report),
                capture_output=True,
                text=True,
                timeout=20,
                env={
                    **os.environ,
                    "ALERT_RECEIVER_URL": f"https://{host}:{server.server_port}/alerts",
                    "ALERT_RECEIVER_TOKEN": token,
                    "ALERT_PANEL_URL": "https://panel.test/dashboard",
                    "SSL_CERT_FILE": str(trust),
                },
            )
            assert not result.stderr, result.stderr
            assert token not in result.stdout
            return result.returncode, json.loads(result.stdout)["deliveries"]

        try:
            for options in ({"trust": unrelated}, {"host": "127.0.0.1"}):
                code, deliveries = command(**options)
                assert code == 1 and all(
                    row["status"] == "failed" for row in deliveries
                )
            assert not requests, "证书拒绝应在 HTTP 投递前发生"
            code, deliveries = command()
            assert code == 1 and all(row["status"] == "failed" for row in deliveries)
            assert not received
            failures[0] = False
            code, deliveries = command(token="wrong-synthetic-token")
            assert code == 1 and not received
            code, delivered = command()
            assert code == 0
            assert [row["state"] for row in delivered] == ["firing", "resolved"]
            assert all(row["status"] == "delivered" for row in delivered)
            code, repeated = command()
            assert code == 0 and repeated == delivered
            assert len(received) == 2
            source = tmp_path / "events.jsonl"
            source.write_text("\n".join(logs), encoding="utf-8")
            code, watched = command(
                module="scripts.watch_skill_alerts",
                extra=(
                    "--log",
                    str(source),
                    "--version",
                    VERSION,
                    "--skill",
                    SKILL,
                    "--start",
                    start.isoformat(),
                    "--until",
                    (datetime.now(UTC) + timedelta(seconds=3)).isoformat(),
                ),
            )
            assert code == 0 and len(watched) == 1
            assert watched[0] == delivered[0]
            assert len(received) == 2
        finally:
            server.shutdown()
            worker.join(timeout=3)
            assert not worker.is_alive()
