"""隔离环回接收端，验证实际 HTTP 回执、失败重试与去重。"""

import json
import threading
from datetime import UTC, datetime
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from scripts.deliver_skill_alerts import deliver, notifications


def test_L10_N05_L10_F05_local_receiver_retries_without_duplicate_notification():
    received = {}
    failed_once = [False]
    at = datetime.now(UTC)
    report = {
        "version": "a" * 40,
        "transitions": [
            {
                "skill_id": "00000000-0000-0000-0000-000000000001",
                "at": at.isoformat(),
                "state": "firing",
            }
        ],
    }
    events = notifications(report, "https://panel.test/dashboard")

    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if not failed_once[0]:
                failed_once[0] = True
                self.send_response(503)
                self.end_headers()
                return
            identifier = self.headers["Idempotency-Key"]
            received.setdefault(identifier, payload)
            body = json.dumps(
                {
                    "event_id": identifier,
                    "delivered": True,
                    "received_at": datetime.now(UTC).isoformat(),
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Receiver) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            destination = f"http://127.0.0.1:{server.server_port}/alerts"
            statuses = [
                deliver(
                    events,
                    destination=destination,
                    token="synthetic",
                    connection_factory=HTTPConnection,
                )[0]["status"]
                for _ in range(3)
            ]
            assert statuses == ["failed", "delivered", "delivered"]
            assert list(received.values()) == events
        finally:
            server.shutdown()
            worker.join(timeout=3)
            assert not worker.is_alive()
