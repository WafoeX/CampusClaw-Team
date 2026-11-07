from contextlib import contextmanager

from app.services.access import AccessDenied
from app.services.materials import unavailable


class ModelGate:
    def __init__(self, repository, database_error):
        self.repository = repository
        self.database_error = database_error

    @contextmanager
    def hold(self, identity):
        try:
            with self.repository.hold(identity.subject_id) as acquired:
                if not acquired:
                    raise AccessDenied(
                        429, 1600, "当前账号已有模型调用，请稍后重试", retry_after=1
                    )
                yield
        except self.database_error:
            raise unavailable() from None
