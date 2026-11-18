"""只在显式隔离演练中加载，使用实际时间与应用请求产生故障。"""

import json
import ssl
import threading
import time
from contextlib import redirect_stdout
from datetime import UTC, datetime, timedelta
from http.client import HTTPSConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from scripts.deliver_skill_alerts import deliver
from scripts.observability_dashboard import render, summarize, utc
from scripts.watch_skill_alerts import watch


def run_skill_alert_drill(
    *, request, frames, service, model, path, skills, target, version, initial
):
    folder = Path("/tmp/alert-drill")
    folder.mkdir()
    source = folder / "events.jsonl"
    source.write_text("".join(json.dumps(row) + "\n" for row in initial))
    started = datetime.now(UTC)
    monotonic = time.monotonic()
    receipts, polls = {}, []
    reject = [True]
    watcher_result = []

    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            assert payload["panel"] == "https://panel.test/drill"
            if reject[0]:
                reject[0] = False
                self.send_response(503)
                self.end_headers()
                return
            assert self.headers["Authorization"] == "Bearer synthetic-drill"
            identifier = self.headers["Idempotency-Key"]
            assert identifier == payload["event_id"]
            receipt = receipts.setdefault(
                identifier,
                {
                    "event_id": identifier,
                    "delivered": True,
                    "received_at": datetime.now(UTC).isoformat(),
                },
            )
            body = json.dumps(receipt).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain("/tmp/receiver.crt", "/tmp/receiver.key")
    trust = ssl.create_default_context(cafile="/tmp/receiver.crt")
    with ThreadingHTTPServer(("127.0.0.1", 0), Receiver) as receiver:
        receiver.socket = tls.wrap_socket(receiver.socket, server_side=True)
        server_thread = threading.Thread(target=receiver.serve_forever, daemon=True)
        server_thread.start()
        endpoint = f"https://localhost:{receiver.server_port}/alerts"

        def send(events, **options):
            return deliver(
                events,
                **options,
                connection_factory=lambda host, port, timeout: HTTPSConnection(
                    host, port, timeout=timeout, context=trust
                ),
            )

        def poll():
            try:
                watcher_result.append(
                    watch(
                        source,
                        version=version,
                        skills=list(skills),
                        start=started,
                        until=started + timedelta(seconds=690),
                        destination=endpoint,
                        panel="https://panel.test/drill",
                        token="synthetic-drill",
                        sender=send,
                        emit=polls.append,
                    )
                )
            except Exception:
                watcher_result.append("failed")

        monitor = threading.Thread(target=poll, daemon=True)
        monitor.start()
        counts = {"fault": 0, "success": 0}
        try:
            with source.open("a", buffering=1) as output, redirect_stdout(output):
                while time.monotonic() - monotonic < 675:
                    elapsed = time.monotonic() - monotonic
                    failing = elapsed < 345
                    model.failure = "invalid" if failing else None
                    response = frames(
                        request(
                            "session",
                            "POST",
                            path,
                            {"question": skills[target]},
                            "alert-drill-" + str(sum(counts.values())),
                        )
                    )
                    assert response[0][1]["data"]["skill"]["id"] == target
                    if failing:
                        assert (
                            response[-1][0] == "error"
                            and response[-1][1]["code"] == 1501
                        )
                        counts["fault"] += 1
                    else:
                        assert response[-1][0] == "done"
                        counts["success"] += 1
                    for _ in range(100):
                        if service.capacity.active == 0:
                            break
                        threading.Event().wait(0.01)
                    assert service.capacity.active == 0
                    # 先满足窗口的最小样本量，再每十秒持续产生实际请求。
                    if sum(counts.values()) >= 20:
                        time.sleep(10)
            monitor.join(timeout=35)
            assert not monitor.is_alive() and watcher_result == [0]
        finally:
            model.failure = None
            receiver.shutdown()
            server_thread.join(timeout=3)

    logs = [
        json.loads(line)
        for line in source.read_text().splitlines()
        if line.startswith("{")
    ]
    snapshot = summarize(
        map(json.dumps, logs),
        version=version,
        skills=list(skills),
        start=min(utc(row.get("completed_at", row["ts"])) for row in initial),
        end=datetime.now(UTC),
    )
    (folder / "panel.html").write_text(render(snapshot))
    (folder / "watch.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in polls)
    )
    deliveries = [row for poll in polls for row in poll["deliveries"]]
    states = [row["state"] for row in deliveries if row["status"] == "delivered"]
    assert states == ["firing", "resolved"]
    report = {
        "version": version,
        "started_at": started.isoformat(),
        "duration_seconds": round(time.monotonic() - monotonic, 2),
        "fault_requests": counts["fault"],
        "success_requests": counts["success"],
        "notification_states": states,
        "failed_deliveries": sum(row["status"] == "failed" for row in deliveries),
        "watcher_exit": watcher_result[0],
        "receipts": list(receipts.values()),
    }
    (folder / "report.json").write_text(json.dumps(report))
    print("ALERT_DRILL " + json.dumps(report))
