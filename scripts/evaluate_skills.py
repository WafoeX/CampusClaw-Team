"""技能槽位固定工程评测；不将结构正确等同教学质量或会话交付。"""

import json
from pathlib import Path

from app.services.access import AccessDenied
from app.services.skills import HINTS, VERSION, render_selection

VALID = [{"hints": [key]} for key in HINTS] + [
    {"hints": ["identify", "relate"]},
    {"hints": ["relate", "plan"]},
    {"hints": ["plan", "check"]},
    {"hints": ["identify", "check"]},
    {"hints": ["identify", "relate", "plan"]},
    {"hints": list(HINTS)},
]
INVALID = [
    {},
    [],
    {"hints": []},
    {"hints": ["answer"]},
    {"hints": [42]},
    {"hints": ["identify", "identify"]},
    {"hints": ["identify"], "answer": "42"},
    {"hints": ["最终答案42"]},
    {"hints": "identify"},
    {"hints": [{}]},
]


def main():
    for payload in VALID:
        assert render_selection(payload) == "\n".join(
            HINTS[key] for key in payload["hints"]
        )
    for payload in INVALID:
        try:
            render_selection(payload)
        except AccessDenied as error:
            assert error.code == 1501
        else:
            raise AssertionError("非法槽位被放行")
    folder = Path("reports/2026-11-04-add-streaming-ai-assistant")
    folder.mkdir(parents=True, exist_ok=True)
    report = {
        "version": VERSION,
        "valid": len(VALID),
        "invalid": len(INVALID),
        "baseline": "此前无技能槽位组件；上游同步应用20条固定回归另行运行",
        "real_gateway": "未执行",
        "session_integration": "真实会话集成结果另列，不由槽位检查判定",
        "semantic_quality": "待最终人工验收",
    }
    (folder / "skills-engineering-eval.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
