"""按路径/方法选择共享 pytest；任一失败、跳过或零用例均非零。"""

import argparse
import html
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/2026-11-04-add-streaming-ai-assistant/apitest"
INJECTION_SCENARIOS = {"SR-F07", "SR-F08", "SR-F09"}


def collect_nodes(*, injection=False):
    files = sorted((ROOT / "apitest/cases").rglob("*.json"))
    if not files:
        raise ValueError("缺少接口用例清单")
    nodes, covered = set(), set()
    for path in files:
        entry = json.loads(path.read_text())
        selected = entry.get("pytest")
        if (
            not isinstance(selected, list)
            or not selected
            or any(
                not isinstance(node, str)
                or not node.startswith("tests/")
                or not (ROOT / node.split("::")[0]).is_file()
                for node in selected
            )
        ):
            raise ValueError("接口用例清单无效：" + str(path.relative_to(ROOT)))
        regression = entry.get("security_regression")
        if regression is not None:
            if (
                not isinstance(regression, dict)
                or regression.get("scenario") not in INJECTION_SCENARIOS
                or any(
                    not isinstance(regression.get(stage), str)
                    or not regression[stage].strip()
                    for stage in ("given", "when", "then")
                )
            ):
                raise ValueError(
                    "注入回归缺少有效场景或三段式：" + str(path.relative_to(ROOT))
                )
            covered.add(regression["scenario"])
        if not injection or regression is not None:
            nodes.update(selected)
    if covered != INJECTION_SCENARIOS:
        raise ValueError(
            "注入回归清单缺项：" + ", ".join(sorted(INJECTION_SCENARIOS - covered))
        )
    return sorted(nodes)


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


def main(*, injection=False, validate_only=False):
    try:
        nodes = collect_nodes(injection=injection)
    except (ValueError, OSError) as error:
        raise SystemExit(str(error)) from None
    if validate_only:
        print(f"接口清单与注入三段式通过，共 {len(nodes)} 个去重入口")
        return 0
    report = REPORT / "injection" if injection else REPORT
    report.mkdir(parents=True, exist_ok=True)
    xml_path = report / "results.xml"
    xml_path.unlink(missing_ok=True)
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
    render_report(xml_path, report / "index.html", status)
    print("本地 HTML：" + str(report / "index.html"))
    return status


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--injection", action="store_true", help="只复跑课程注入三件套")
    parser.add_argument("--validate-only", action="store_true", help="只核对清单完整性")
    options = parser.parse_args()
    raise SystemExit(
        main(injection=options.injection, validate_only=options.validate_only)
    )
