"""从同一候选的结构化运行日志生成本地观测面板。"""

import argparse
import json
import math
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

WINDOW = timedelta(minutes=5)
SKILL_RESULTS = {"succeeded", "failed", "interrupted"}
TEMPLATE = Path(__file__).with_suffix(".html")


def utc(value):
    if not isinstance(value, str):
        raise ValueError("时间须为带时区的 ISO 8601 字符串")
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None:
        raise ValueError("时间须包含时区")
    try:
        return stamp.astimezone(UTC)
    except OverflowError:
        raise ValueError("时间超出可表示的 UTC 范围") from None


def utc_label(stamp):
    return stamp.isoformat().removesuffix("+00:00") + "Z"


@dataclass
class Bucket:
    calls: dict[str, Counter]
    api_ms: list[float] = field(default_factory=list)
    backlog: tuple[datetime, int] | None = None

    def report(self, start):
        skills = {}
        for skill, statuses in self.calls.items():
            calls = statuses.total()
            skills[skill] = {
                "calls": calls,
                "failed": statuses["failed"],
                "interrupted": statuses["interrupted"],
                "error_percent": statuses["failed"] * 100 / calls if calls else None,
            }
        ordered = sorted(self.api_ms)
        return {
            "start": utc_label(start),
            "skills": skills,
            "api_samples": len(ordered),
            "api_p95_ms": ordered[math.ceil(len(ordered) * 0.95) - 1]
            if ordered
            else None,
            "pending": self.backlog[1] if self.backlog else None,
        }


def summarize(lines, *, version, skills, start, end):
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("采样时间须包含时区")
    if not timedelta(0) < end - start <= timedelta(days=1):
        raise ValueError("采样范围须大于零且至多 24 小时")
    if not skills or len(skills) != len(set(skills)):
        raise ValueError("须提供互不重复的技能 ID")
    buckets = [
        Bucket({skill: Counter() for skill in skills})
        for _ in range(math.ceil((end - start) / WINDOW))
    ]
    for line in lines:
        try:
            row = json.loads(line)
        except (json.JSONDecodeError, RecursionError):
            continue
        if not isinstance(row, dict) or row.get("version") != version:
            continue
        module = row.get("module")
        if module not in ("skill_execution", "http", "teaching_backlog"):
            continue
        try:
            stamp = utc(
                row.get("completed_at" if module == "skill_execution" else "ts")
            )
        except ValueError:
            continue
        if not start <= stamp < end:
            continue
        bucket = buckets[(stamp - start) // WINDOW]
        if module == "skill_execution":
            skill = row.get("skill_id")
            status = row.get("status")
            if (
                isinstance(skill, str)
                and skill in bucket.calls
                and isinstance(status, str)
                and status in SKILL_RESULTS
            ):
                bucket.calls[skill][status] += 1
        elif module == "http":
            route = row.get("route")
            duration = row.get("duration_ms")
            if (
                isinstance(route, str)
                and route.startswith("/api/v1/")
                and type(duration) in (int, float)
                and 0 <= duration <= sys.float_info.max
            ):
                bucket.api_ms.append(duration)
        else:
            states = row.get("states")
            if isinstance(states, dict):
                pending = states.get("pending", 0)
                if type(pending) is int and pending >= 0:
                    if bucket.backlog is None or stamp >= bucket.backlog[0]:
                        bucket.backlog = (stamp, pending)
    return {
        "version": version,
        "skills": list(skills),
        "end": utc_label(end),
        "windows": [
            bucket.report(start + index * WINDOW)
            for index, bucket in enumerate(buckets)
        ],
    }


def render(report):
    payload = json.dumps(report, ensure_ascii=True, allow_nan=False)
    return TEMPLATE.read_text(encoding="utf-8").replace(
        "__OBSERVABILITY_DATA__", payload.replace("<", "\\u003c")
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="完整候选提交号")
    parser.add_argument("--skill", type=UUID, action="append", required=True)
    parser.add_argument("--start", type=utc, required=True)
    parser.add_argument("--end", type=utc, required=True)
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[0-9a-f]{40}", args.version):
        parser.error("--version 须为 40 位小写十六进制提交号")
    try:
        report = summarize(
            sys.stdin,
            version=args.version,
            skills=[str(skill) for skill in args.skill],
            start=args.start,
            end=args.end,
        )
    except ValueError as error:
        parser.error(str(error))
    print(render(report))


if __name__ == "__main__":
    main()
