"""向部署指定的 HTTPS 收件端投递技能告警并核对回执。"""

import argparse
import hashlib
import json
import os
import re
import sys
from contextlib import closing
from datetime import UTC, datetime, timedelta
from http.client import HTTPException, HTTPSConnection
from urllib.parse import urlsplit
from uuid import UUID

from scripts.observability_dashboard import utc, utc_label


def https_url(value):
    try:
        url = urlsplit(value)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.port == 0
        ):
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError("须配置无凭据、查询和片段的 HTTPS 地址") from None
    return value


def notifications(report, panel):
    version = report["version"]
    if not isinstance(version, str) or not re.fullmatch(r"[a-f0-9]{40}", version):
        raise ValueError("候选提交号无效")
    active = set()
    seen = set()
    previous = None
    result = []
    for row in report["transitions"]:
        skill, at, state = str(UUID(row["skill_id"])), utc(row["at"]), row["state"]
        if previous is not None and at < previous:
            raise ValueError("转换记录须按时间排序")
        previous = at
        if state == "firing":
            active.add(skill)
        elif state == "normal" and skill in active:
            active.remove(skill)
        elif state in {"normal", "pending", "no_data"}:
            continue
        else:
            raise ValueError("未知的告警状态")
        event = {
            "version": version,
            "skill_id": skill,
            "at": utc_label(at),
            "state": "resolved" if state == "normal" else "firing",
            "panel": panel,
        }
        event_id = hashlib.sha256(
            json.dumps(
                {key: value for key, value in event.items() if key != "panel"},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        if event_id not in seen:
            result.append({"event_id": event_id, **event})
            seen.add(event_id)
    return result


def deliver(
    events,
    *,
    destination,
    token,
    connection_factory=HTTPSConnection,
    clock=lambda: datetime.now(UTC),
):
    target = urlsplit(destination)
    records = []
    for event in events:
        record = {
            "event_id": event["event_id"],
            "state": event["state"],
            "status": "failed",
        }
        try:
            with closing(
                connection_factory(target.hostname, target.port, timeout=5)
            ) as connection:
                connection.request(
                    "POST",
                    target.path or "/",
                    body=json.dumps(event).encode(),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": "Bearer " + token,
                        "Idempotency-Key": event["event_id"],
                    },
                )
                response = connection.getresponse()
                if response.status not in (200, 201):
                    raise ValueError
                body = response.read(8193)
                if len(body) > 8192:
                    raise ValueError
                receipt = json.loads(body)
            received = clock()
            confirmed = utc(receipt["received_at"])
            triggered = utc(event["at"])
            if (
                receipt["event_id"] != event["event_id"]
                or receipt["delivered"] is not True
                or not triggered <= confirmed <= received + timedelta(seconds=5)
            ):
                raise ValueError
            record["status"] = (
                "delivered"
                if confirmed - triggered <= timedelta(seconds=120)
                else "late"
            )
            record["confirmed_at"] = utc_label(confirmed)
        except (
            HTTPException,
            OSError,
            ValueError,
            KeyError,
            TypeError,
            RecursionError,
        ):
            pass
        records.append(record)
    return records


def configuration():
    destination = https_url(os.environ.get("ALERT_RECEIVER_URL"))
    panel = https_url(os.environ.get("ALERT_PANEL_URL"))
    token = os.environ.get("ALERT_RECEIVER_TOKEN", "")
    if (
        not token
        or len(token) > 4096
        or any(ord(c) < 33 or ord(c) > 126 for c in token)
    ):
        raise ValueError("须配置有效的收件端令牌")
    return destination, panel, token


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    try:
        destination, panel, token = configuration()
        events = notifications(json.load(sys.stdin), panel)
    except (ValueError, KeyError, TypeError, RecursionError):
        parser.error(
            "请检查告警报告与 ALERT_RECEIVER_URL、ALERT_PANEL_URL、ALERT_RECEIVER_TOKEN"
        )
    records = deliver(events, destination=destination, token=token)
    print(json.dumps({"deliveries": records}, ensure_ascii=False))
    return int(any(row["status"] != "delivered" for row in records))


if __name__ == "__main__":
    raise SystemExit(main())
