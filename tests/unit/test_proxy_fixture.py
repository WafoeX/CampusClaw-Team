"""ST-F06/F07：慢上游夹具对FIN/RST均回收活动记录，不伪造成功。"""

import io
import json
from unittest.mock import Mock

import pytest

from tests.integration import streaming_probe_worker as worker


@pytest.mark.parametrize("reset", [False, True])
def test_ST_F07_upstream_disconnect_always_clears_metrics(monkeypatch, reset):
    handlers = []

    def server(_address, handler):
        handlers.append(handler)
        return Mock()

    monkeypatch.setattr(worker, "ThreadingHTTPServer", server)
    monkeypatch.setattr(worker.socket_select, "select", lambda *args: ([True], [], []))
    worker.serve_upstream()
    handler = object.__new__(handlers[0])
    body = json.dumps(
        {
            "messages": [
                {},
                {
                    "content": json.dumps(
                        {"question": "电压 synthetic-reset", "paragraph": 2}
                    )
                },
            ]
        }
    )
    handler.path = "/chat/completions"
    handler.headers = {"Content-Length": str(len(body.encode()))}
    handler.rfile = io.BytesIO(body.encode())
    handler.connection = Mock()
    if reset:
        handler.connection.recv.side_effect = ConnectionResetError
    else:
        handler.connection.recv.return_value = b""
    handler.do_POST()
    handler.path = "/metrics"
    handler.send_response = Mock()
    handler.send_header = Mock()
    handler.end_headers = Mock()
    handler.wfile = io.BytesIO()
    handler.do_GET()
    metrics = json.loads(handler.wfile.getvalue())
    assert metrics["active"] == []
    assert metrics["cancelled"] == ["synthetic-reset"]
    assert metrics["completed"] == []
