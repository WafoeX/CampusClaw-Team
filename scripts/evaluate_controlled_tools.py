"""以固定合成问题验证真实课程网关与独立 MCP 服务的最小互操作。"""

import json
import os
import secrets
import sys
import time
from dataclasses import replace
from hashlib import sha256
from ipaddress import ip_network
from pathlib import Path
from threading import Thread

from werkzeug.serving import make_server

from app.adapters.chat_client import ChatClient
from app.adapters.index_clients import IndexDependencyError
from app.adapters.tool_protocol import ToolProtocol
from app.adapters.tool_transport import ToolDependencyError, ToolTransport
from app.config import ChatSettings
from app.services.tool_runner import PLANNER
from app.tool_config import load_tool_directory

ROOT = Path(__file__).resolve().parents[1]
QUESTION = (
    "我在练习一元一次方程。请先调用提供的提示工具，主题 linear_equation，阶段 start。"
)
REF = "formula_hint@teaching"


def gateway_configuration():
    env = dict(os.environ)
    if (ROOT / ".env").is_file():
        for line in (ROOT / ".env").read_text().splitlines():
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env.setdefault(key, value.strip().strip('"').strip("'"))
    try:
        config = ChatSettings.load(env)
    except ValueError:
        config = None
    if not config or not config.api_key:
        raise SystemExit("缺少真实课程网关配置")
    return config


def main():
    config = gateway_configuration()
    sys.path.insert(0, str(ROOT / "mcp-server"))
    from teaching_server import create_app

    token = secrets.token_urlsafe(32)
    os.environ["MCP_SERVICE_TOKEN"] = token
    target = load_tool_directory(
        {"MCP_SERVICE_NETWORK": "172.20.0.0/24", "MCP_SERVICE_TOKEN": token}
    )["teaching"]
    report = {
        "case": "controlled-tools-real-gateway-v1",
        "input_sha256": sha256(QUESTION.encode()).hexdigest(),
        "prompt_sha256": sha256(PLANNER.encode()).hexdigest(),
        "model": config.model,
        "configuration": config.version,
        "temperature": config.temperature,
        "model_calls": 0,
        "mcp_calls": 0,
        "passed": False,
    }
    with make_server("127.0.0.1", 0, create_app(), threaded=True) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        target = replace(
            target,
            host="127.0.0.1",
            port=server.server_port,
            network=ip_network("127.0.0.1/32"),
        )
        protocol = ToolProtocol(ToolTransport())
        session = None
        try:
            policy = target.tools["formula_hint"]
            inputs = {
                "question": QUESTION,
                "candidates": [{"reference": REF, "definition": policy.definition}],
                "tool_data": [],
            }
            report["model_calls"] += 1
            started = time.monotonic()
            plan = ChatClient(config).complete_once(
                [
                    {"role": "system", "content": PLANNER},
                    {"role": "user", "content": json.dumps(inputs, ensure_ascii=False)},
                ],
                started + 15,
            )
            report["model_ms"] = round((time.monotonic() - started) * 1000, 2)
            calls = plan.get("calls") if isinstance(plan, dict) else None
            if (
                not isinstance(calls, list)
                or len(calls) != 1
                or not isinstance(calls[0], dict)
                or calls[0].get("tool") != REF
                or calls[0].get("arguments")
                != {"topic": "linear_equation", "stage": "start"}
            ):
                report["failure"] = "proposal"
            else:
                started = time.monotonic()
                session, catalog = protocol.discover(target, started + 3)
                report["connect_ms"] = round((time.monotonic() - started) * 1000, 2)
                if "formula_hint" not in {entry["name"] for entry in catalog}:
                    raise ToolDependencyError("catalog")
                started = time.monotonic()
                report["mcp_calls"] += 1
                result = protocol.call(
                    target, session, "formula_hint", calls[0]["arguments"], started + 2
                )
                report["mcp_ms"] = round((time.monotonic() - started) * 1000, 2)
                report["passed"] = result["hint_id"] == "linear_equation:start"
        except IndexDependencyError as error:
            report["failure"] = error.stage
        except ToolDependencyError:
            report["failure"] = "mcp"
        finally:
            protocol.close(target, session, time.monotonic() + 1)
            server.shutdown()
            worker.join(timeout=2)
    output = ROOT / "reports/2026-11-04-add-controlled-mcp-tools/real-gateway.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
