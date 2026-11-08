"""按路径/方法选择共享 pytest；任一失败、跳过或零用例均非零。"""

import html
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/2026-11-04-add-streaming-ai-assistant/apitest"


def render_report(xml_path, output, status):
    rows = []
    if xml_path.is_file():
        for case in ET.parse(xml_path).iter("testcase"):
            state = "通过"
            if case.find("failure") is not None or case.find("error") is not None:
                state = "失败"
            elif case.find("skipped") is not None:
                state = "跳过（门禁失败）"
            # 不复制失败正文、stdout、请求或数据库内容到 HTML。
            rows.append(
                "<tr>"
                + "".join(
                    f"<td>{html.escape(value)}</td>"
                    for value in (
                        case.get("classname", ""),
                        case.get("name", ""),
                        state,
                        case.get("time", ""),
                    )
                )
                + "</tr>"
            )
    output.write_text(
        '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>接口测试</title>'
        f"<h1>共享接口回归</h1><p>退出码：{status}；执行 {len(rows)} 项。"
        "真实 MySQL/Qdrant 集成使用合成隔离库；模型采用可控替身。</p>"
        "<table><tr><th>模块</th><th>用例</th><th>结果</th><th>秒</th></tr>"
        + "".join(rows)
        + "</table></html>"
    )


def main():
    REPORT.mkdir(parents=True, exist_ok=True)
    xml_path = REPORT / "results.xml"
    xml_path.unlink(missing_ok=True)
    files = sorted((ROOT / "apitest/cases").rglob("*.json"))
    if not files:
        raise SystemExit("缺少接口用例清单")
    nodes = sorted(
        {node for path in files for node in json.loads(path.read_text())["pytest"]}
    )
    if not nodes or any(
        not node.startswith("tests/") or not (ROOT / node.split("::")[0]).is_file()
        for node in nodes
    ):
        raise SystemExit("接口用例清单无效")
    env = dict(os.environ)
    env.pop("PYTEST_ADDOPTS", None)
    status = subprocess.run(
        [
            sys.executable,
            "scripts/check_pytest.py",
            "-q",
            *nodes,
            f"--junitxml={xml_path}",
        ],
        cwd=ROOT,
        env=env,
        check=False,
    ).returncode
    render_report(xml_path, REPORT / "index.html", status)
    print("本地 HTML：" + str(REPORT / "index.html"))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
