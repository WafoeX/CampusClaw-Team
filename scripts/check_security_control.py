"""用隔离候选的产物副本复跑真实资产门禁。"""

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

SCOPES = {
    "history",
    "worktree",
    "frontend",
    "logs",
    "dependencies",
    "app.tar",
    "mcp-server.tar",
}
ROOT = Path(__file__).resolve().parents[1]


def placeholder_boundary(edge):
    return f"-----{edge} PRIVATE" + " KEY-----\n"


def run_gate(assets, cache, candidate, *, expect_marker):
    result = subprocess.run(
        [
            "make",
            "check-security",
            f"SECURITY_ASSETS={assets}",
            f"TRIVY_CACHE={cache}",
            f"SECURITY_CANDIDATE={candidate}",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )
    print(result.stdout, end="")
    print(result.stderr, end="")
    print(f"make_exit={result.returncode}", flush=True)
    rows = [
        json.loads(line)
        for line in result.stdout.splitlines()
        if line.startswith('{"scope":')
    ]
    by_scope = {row["scope"]: row for row in rows}
    if len(rows) != len(SCOPES) or by_scope.keys() != SCOPES:
        raise SystemExit("资产门禁未给出全部分项")
    expected_exit = 2 if expect_marker else 0
    if result.returncode != expected_exit:
        raise SystemExit("资产门禁总退出码不符合对照")
    for scope, row in by_scope.items():
        has_marker = scope == "frontend" and expect_marker
        if row["exit"] != int(has_marker):
            raise SystemExit(f"{scope} 分项未达到预期")
        if scope == "dependencies":
            if (row["high"], row["critical"]) != (0, 0):
                raise SystemExit("候选的锁依赖审计未通过")
        elif row["secrets"] != int(has_marker):
            raise SystemExit(f"{scope} 命中数不符合对照")
    return by_scope["dependencies"]["database_updated"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assets", type=Path)
    parser.add_argument("--cache", type=Path, default=ROOT / "reports/trivy-cache")
    args = parser.parse_args()
    source = args.assets.resolve(strict=True)
    candidate = (source / "revision").read_text().strip()
    with tempfile.TemporaryDirectory(
        prefix="security-control-", dir=ROOT / "reports"
    ) as scratch:
        assets = Path(scratch) / "assets"
        shutil.copytree(source, assets)
        # 只写入忽略的临时扫描副本。占位文本没有任何有效密钥材料。
        marker = assets / "frontend" / "scanner-control.txt"
        with marker.open("x") as sample:
            sample.write(
                placeholder_boundary("BEGIN")
                + "CampusClaw synthetic scanner fixture only, no valid key data.\n"
                + placeholder_boundary("END")
            )
        print("合成标记对照", flush=True)
        first_database = run_gate(
            assets, args.cache.resolve(), candidate, expect_marker=True
        )
        marker.unlink()
        print("清理后复跑", flush=True)
        second_database = run_gate(
            assets, args.cache.resolve(), candidate, expect_marker=False
        )
        if first_database != second_database:
            raise SystemExit("两轮扫描的漏洞库更新时间不同")


if __name__ == "__main__":
    main()
