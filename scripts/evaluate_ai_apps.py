"""同步应用固定工程校验；--real显式启用三次合成课程网关烟测，不输出凭据或模型正文。"""

import argparse
import json
import os
import time
from pathlib import Path

from app.adapters.chat_client import ChatClient, ChatProtocolError
from app.adapters.index_clients import IndexDependencyError
from app.config import ChatSettings
from app.services.access import AccessDenied
from app.services.ai_contracts import (
    APP_POLICIES,
    PROMPT_VERSION,
    render_prompt,
    run_messages,
    validate_output,
    variables,
)

VALID = [
    {"text": value}
    for value in (
        "学习建议",
        "中文😀",
        " a ",
        "一\n二",
        "<script>仅作为文本</script>",
        "{{input}}数据",
        "1. 复习\n2. 练习",
        "学习计划：每天阅读",
        "独立练习：解释原子性",
        "x" * 12000,
    )
]
INVALID = [
    {},
    [],
    {"text": False},
    {"text": 123},
    {"text": ""},
    {"text": "a" * 12001},
    {"text": "\0"},
    {"text": "\ud800"},
    {"text": "越权", "tool_calls": [{}]},
    {"text": "不可信", "role": "system"},
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--real", action="store_true")
    args = parser.parse_args()
    passed = 0
    for payload in VALID:
        assert validate_output(payload) == payload["text"].strip()
        passed += 1
    for payload in INVALID:
        try:
            validate_output(payload)
        except AccessDenied as error:
            assert error.code == 1501
        else:
            raise AssertionError("非法输出未被拒绝")
        passed += 1
    values = variables({"input": "{{audience}}合成段落", "audience": "同学"})
    prompt = "请给{{audience}}提供帮助：{{input}}"
    for app_key in APP_POLICIES:
        messages = run_messages(app_key, prompt, values)
        assert json.loads(messages[1]["content"])["rendered_prompt"] == render_prompt(
            prompt, values
        )
        assert "{{audience}}合成段落" not in messages[0]["content"]
    report = {
        "version": PROMPT_VERSION,
        "baseline": "首次同步应用，无旧应用入口；上游单次问答回归单列",
        "deterministic": {
            "valid": len(VALID),
            "invalid": len(INVALID),
            "passed": passed,
        },
        "real_gateway": {"state": "未执行"},
    }
    if args.real:
        env = dict(os.environ)
        for line in Path(".env").read_text().splitlines():
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env[key] = value.strip().strip('"').strip("'")
        config = ChatSettings.load(env)
        if config is None or not config.api_key:
            raise ValueError("缺课程模型配置")
        events = []
        client = ChatClient(config, on_result=lambda **event: events.append(event))
        cases = {
            "polish": "请润色这句话：数据库事务保证一组写入共同提交。",
            "learning_plan": "我计划一周内复习数据库事务，每天学习二十分钟。",
            "practice": "生成一道关于数据库事务原子性的独立学习练习。",
        }
        samples = []
        for app_key, input_text in cases.items():
            started = time.monotonic()
            payload = client.complete(
                run_messages(
                    app_key,
                    "{{input}}",
                    variables({"input": input_text, "audience": "同学"}),
                ),
                started + 35,
            )
            output = validate_output(payload)
            samples.append(
                {
                    "app_key": app_key,
                    "valid_structure": True,
                    "characters": len(output),
                    "duration_ms": round((time.monotonic() - started) * 1000, 2),
                }
            )
        report["real_gateway"] = {
            "state": "通过",
            "request_model": config.model,
            "model_config": config.version,
            "samples": samples,
            "events": events,
            "semantic_quality": "待最终人工验收，不以结构正确代替",
        }
    folder = Path("reports/2026-11-04-add-streaming-ai-assistant")
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (
        "apps-real-smoke.json" if args.real else "apps-engineering-eval.json"
    )
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "engineering_passed": passed,
                "real_gateway": report["real_gateway"]["state"],
                "report": str(target),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, AccessDenied, IndexDependencyError, ChatProtocolError):
        raise SystemExit(
            "同步应用评测失败，请检查私有配置、模型结构或依赖；未输出凭据和模型正文。"
        ) from None
