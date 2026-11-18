"""离线评估技能错误率告警，输出触发和恢复状态供通知流程取证。"""

import argparse
import json
import re
import sys
from collections import Counter, deque
from datetime import timedelta
from uuid import UUID

from scripts.observability_dashboard import SKILL_RESULTS, WINDOW, utc, utc_label

STEP = timedelta(seconds=15)


def evaluate(lines, *, version, skills, start, end):
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("评估时间须包含时区")
    if not timedelta(0) < end - start <= timedelta(days=1):
        raise ValueError("评估范围须大于零且至多 24 小时")
    if not skills or len(skills) != len(set(skills)):
        raise ValueError("须提供互不重复的技能 ID")
    events = []
    for line in lines:
        try:
            row = json.loads(line)
        except (ValueError, RecursionError):
            continue
        if (
            not isinstance(row, dict)
            or row.get("module") != "skill_execution"
            or row.get("version") != version
        ):
            continue
        skill, status = row.get("skill_id"), row.get("status")
        if not isinstance(skill, str) or not isinstance(status, str):
            continue
        if skill not in skills or status not in SKILL_RESULTS:
            continue
        try:
            stamp = utc(row.get("completed_at"))
        except ValueError:
            continue
        if start - WINDOW < stamp < end:
            events.append((stamp, skill, status))
    future = deque(sorted(events))
    active = deque()
    counts = {skill: Counter() for skill in skills}
    pending = dict.fromkeys(skills)
    states = dict.fromkeys(skills, "no_data")
    transitions = []
    sample = start
    while sample < end:
        while future and future[0][0] <= sample:
            event = future.popleft()
            active.append(event)
            counts[event[1]][event[2]] += 1
        while active and active[0][0] <= sample - WINDOW:
            _, skill, status = active.popleft()
            counts[skill][status] -= 1
        for skill in skills:
            calls = counts[skill].total()
            failed = counts[skill]["failed"]
            previous = states[skill]
            if calls < 20:
                state = "no_data"
                pending[skill] = None
            elif failed * 100 > calls:
                if pending[skill] is None:
                    pending[skill] = sample
                state = "firing" if sample - pending[skill] >= WINDOW else "pending"
            else:
                state = "normal"
                pending[skill] = None
            if state != previous:
                transitions.append(
                    {
                        "at": utc_label(sample),
                        "skill_id": skill,
                        "state": state,
                        "calls": calls,
                        "failed": failed,
                        "error_percent": failed * 100 / calls if calls else None,
                        "notification": "required" if state == "firing" else "none",
                    }
                )
            states[skill] = state
        sample += STEP
    return {
        "version": version,
        "start": utc_label(start),
        "end": utc_label(end),
        "rule": {
            "window_seconds": 300,
            "minimum_calls": 20,
            "error_percent_above": 1,
            "hold_seconds": 300,
            "evaluation_seconds": 15,
        },
        "states": states,
        "transitions": transitions,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--skill", type=UUID, action="append", required=True)
    parser.add_argument("--start", type=utc, required=True)
    parser.add_argument("--end", type=utc, required=True)
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[0-9a-f]{40}", args.version):
        parser.error("--version 须为 40 位小写十六进制提交号")
    try:
        result = evaluate(
            sys.stdin,
            version=args.version,
            skills=[str(skill) for skill in args.skill],
            start=args.start,
            end=args.end,
        )
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
