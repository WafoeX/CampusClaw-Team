"""版本化 Kafka 消息与教学任务状态。"""

import json
from dataclasses import asdict, dataclass
from uuid import UUID

CANDIDATES = "question_generation"
TASK_TOPIC = "campusclaw.teaching.candidates.v1"
DEAD_TOPIC = "campusclaw.teaching.candidates.dead.v1"
CONSUMER_GROUP = "campusclaw.teaching.candidates.v1"
ACTIVE = ("pending", "running", "retry_wait")
REPLAYABLE = ("failed", "dead_letter")
RETRY_SECONDS = (5, 15, 45, 120)
JOB_LEASE_SECONDS = 90
OUTBOX_LEASE_SECONDS = 20
RECOVERY_SECONDS = 300
CLASS_CAPACITY = 20


def unique_fields(pairs):
    data = {}
    for name, value in pairs:
        if name in data:
            raise ValueError("duplicate message field")
        data[name] = value
    return data


@dataclass(frozen=True)
class Event:
    event_id: str
    task_id: str
    generation: int
    trace_id: str
    version: int = 1

    def payload(self):
        return asdict(self)

    @classmethod
    def parse(cls, key, value):
        if value is None or len(value) > 512:
            raise ValueError("invalid message size")
        data = json.loads(value, object_pairs_hook=unique_fields)
        if not isinstance(data, dict) or set(data) != set(cls.__dataclass_fields__):
            raise ValueError("invalid message fields")
        if type(data["version"]) is not int or data["version"] != 1:
            raise ValueError("unsupported message version")
        if type(data["generation"]) is not int or data["generation"] < 1:
            raise ValueError("invalid generation")
        for name in ("event_id", "task_id", "trace_id"):
            value = data[name]
            if not isinstance(value, str) or str(UUID(value)) != value:
                raise ValueError("invalid message identifier")
        if key != data["task_id"].encode():
            raise ValueError("invalid message key")
        return cls(**data)


class JobFailure(Exception):
    def __init__(self, code, *, reason=None, transient=False, cancelled=False):
        super().__init__(code)
        self.code = code
        self.reason = reason
        self.transient = transient
        self.cancelled = cancelled


class JobNotSettled(Exception):
    """The current event must remain at its Kafka position until it settles."""
