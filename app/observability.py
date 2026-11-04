import json
import sys
from datetime import UTC, datetime
from threading import Lock

LOG_LOCK = Lock()


def utc_time():
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def log_event(module, version, *, level="INFO", request_id=None, **details):
    line = json.dumps(
        {
            "ts": utc_time(),
            "level": level,
            "module": module,
            "request_id": request_id,
            "version": version,
            **details,
        },
        ensure_ascii=True,
    )
    with LOG_LOCK:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()
