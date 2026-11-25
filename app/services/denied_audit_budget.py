"""单进程拒绝审计写预算；仅在短锁内计数，不在锁内访问数据库。"""

from enum import Enum, auto
from threading import Lock
from time import monotonic


class DeniedAuditResult(Enum):
    STORED = auto()
    UNAVAILABLE = auto()
    SUPPRESSED = auto()
    LIMIT_REACHED = auto()


class DeniedAuditBudget:
    def __init__(self, per_subject=60, total=600, *, clock=monotonic):
        if not 1 <= per_subject <= total <= 10000:
            raise ValueError("拒绝审计预算无效")
        self.per_subject = per_subject
        self.total = total
        self.clock = clock
        self._lock = Lock()
        self._window = None
        self._subjects = {}
        self._used = 0
        self._notified = False

    def reserve(self, subject):
        with self._lock:
            window = int(self.clock() // 60)
            if window != self._window:
                self._window = window
                self._subjects.clear()
                self._used = 0
                self._notified = False
            used = self._subjects.get(subject, 0)
            if self._used >= self.total or used >= self.per_subject:
                result = (
                    DeniedAuditResult.SUPPRESSED
                    if self._notified
                    else DeniedAuditResult.LIMIT_REACHED
                )
                self._notified = True
                return result
            self._subjects[subject] = used + 1
            self._used += 1
            return None
