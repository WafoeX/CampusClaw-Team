"""MySQL 连接级命名锁，跨 worker 共享；网络 I/O 期间无数据库事务。"""

from contextlib import contextmanager
from hashlib import sha256

from sqlalchemy import func, select


class ModelLeaseRepository:
    def __init__(self, engine):
        self.engine = engine

    @contextmanager
    def hold(self, subject_id):
        name = sha256(
            f"model-lease:{self.engine.url.database}:{subject_id}".encode()
        ).hexdigest()
        with self.engine.connect().execution_options(
            isolation_level="AUTOCOMMIT"
        ) as connection:
            acquired = connection.scalar(select(func.get_lock(name, 0))) == 1
            try:
                yield acquired
            finally:
                if acquired:
                    try:
                        connection.scalar(select(func.release_lock(name)))
                    except Exception:
                        connection.invalidate()
                        raise
