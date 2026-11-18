"""按固定起点轮询完整候选日志，评估告警并重试未确认通知。"""

import argparse
import json
import re
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from scripts.deliver_skill_alerts import configuration, deliver, notifications
from scripts.evaluate_skill_alerts import STEP, evaluate
from scripts.observability_dashboard import utc, utc_label


def watch(
    path,
    *,
    version,
    skills,
    start,
    until,
    destination,
    panel,
    token,
    clock=lambda: datetime.now(UTC),
    sleep=time.sleep,
    sender=deliver,
    emit=lambda record: print(json.dumps(record, ensure_ascii=False), flush=True),
):
    if not timedelta(0) < until - start <= timedelta(days=1):
        raise ValueError("轮询范围须大于零且至多 24 小时")
    if not start <= clock() < until:
        raise ValueError("当前时间须位于指定的轮询范围内")
    receipts = {}
    previous_size = 0
    while (now := clock()) < until:
        size = path.stat().st_size
        if size < previous_size:
            raise ValueError("源日志已截短，请保留完整日志后重启")
        previous_size = size
        with path.open(encoding="utf-8") as source:
            report = evaluate(
                source,
                version=version,
                skills=skills,
                start=start,
                end=min(now + timedelta(microseconds=1), until),
            )
        pending = [
            event
            for event in notifications(report, panel)
            if receipts.get(event["event_id"], {}).get("status")
            not in {"delivered", "late"}
        ]
        records = []
        blocked = set()
        for event in pending:
            if event["skill_id"] in blocked:
                continue
            delivered = sender([event], destination=destination, token=token)
            records.extend(delivered)
            if any(record["status"] == "failed" for record in delivered):
                blocked.add(event["skill_id"])
        receipts.update({record["event_id"]: record for record in records})
        emit({"at": utc_label(now), "states": report["states"], "deliveries": records})
        delay = min(STEP.total_seconds(), (until - clock()).total_seconds())
        if delay > 0:
            sleep(delay)
    return int(any(row["status"] != "delivered" for row in receipts.values()))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--skill", type=UUID, action="append", required=True)
    parser.add_argument("--start", type=utc, required=True)
    parser.add_argument("--until", type=utc, required=True)
    args = parser.parse_args(argv)
    try:
        destination, panel, token = configuration()
        if not re.fullmatch(r"[a-f0-9]{40}", args.version):
            raise ValueError("候选提交号无效")
        return watch(
            args.log,
            version=args.version,
            skills=[str(skill) for skill in args.skill],
            start=args.start,
            until=args.until,
            destination=destination,
            panel=panel,
            token=token,
        )
    except (OSError, ValueError, TypeError, KeyError):
        parser.error("请检查完整候选日志、时间范围、技能及通知环境配置")


if __name__ == "__main__":
    raise SystemExit(main())
