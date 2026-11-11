"""独立 HTTP 协议夹具，验证 POST SSE 得到匹配响应即可结束。"""

import json
import time
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_network
from threading import Event, Thread

from app.adapters.tool_protocol import PROTOCOL, ToolProtocol
from app.adapters.tool_transport import ToolTransport
from app.tool_config import load_tool_directory

released = Event()
requests = []


class Fixture(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        requests.append((body["method"], self.headers.get("MCP-Protocol-Version")))
        if body["method"] == "notifications/initialized":
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        result = (
            {"protocolVersion": PROTOCOL, "capabilities": {"tools": {}}}
            if body["method"] == "initialize"
            else {
                "tools": [{"name": "formula_hint", "inputSchema": {"type": "object"}}]
            }
        )
        response = json.dumps({"jsonrpc": "2.0", "id": body["id"], "result": result})
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        data = ("data: " + response + "\r\n\r\n").encode()
        # 固定每帧分两段并保持连接，夹具在客户端返回后再释放。
        for chunk in (data[:13], data[13:]):
            self.wfile.write(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
            self.wfile.flush()
        released.wait(5)
        self.close_connection = True

    def log_message(self, *_):
        pass


target = load_tool_directory(
    {"MCP_SERVICE_NETWORK": "172.20.0.0/24", "MCP_SERVICE_TOKEN": "synthetic"}
)["teaching"]
with ThreadingHTTPServer(("127.0.0.1", 0), Fixture) as server:
    target = replace(
        target,
        host="127.0.0.1",
        port=server.server_port,
        network=ip_network("127.0.0.1/32"),
    )
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        session, catalog = ToolProtocol(ToolTransport()).discover(
            target, time.monotonic() + 2
        )
        assert session is None
        assert [item["name"] for item in catalog] == ["formula_hint"]
        assert requests == [
            ("initialize", None),
            ("notifications/initialized", PROTOCOL),
            ("tools/list", PROTOCOL),
        ]
    finally:
        released.set()
        server.shutdown()
        worker.join(timeout=2)
print("独立 POST SSE 夹具互操作通过")
