from hashlib import sha256

from app.services.access import AccessDenied


class RequestLimiter:
    def __init__(self, repository, database_error):
        self.repository = repository
        self.database_error = database_error

    def check(self, scope, principal):
        digest = sha256(f"{scope}\0{principal}".encode()).digest()
        try:
            allowed, retry_after = self.repository.consume(digest, 60)
        except self.database_error:
            raise AccessDenied(503, 1500, "依赖服务暂不可用，请稍后重试") from None
        if not allowed:
            raise AccessDenied(
                429, 1600, "操作过于频繁，请稍后重试", retry_after=retry_after
            )
