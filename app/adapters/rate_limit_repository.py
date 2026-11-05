from datetime import timedelta

from sqlalchemy import func, select, text
from sqlalchemy.dialects.mysql import insert

from app.adapters.rate_limit_schema_v3 import request_limits


class RateLimitRepository:
    def __init__(self, engine):
        self.engine = engine

    def consume(self, digest, limit):
        with self.engine.begin() as connection:
            now = connection.scalar(select(func.utc_timestamp(6)))
            window = now.replace(second=0, microsecond=0)
            connection.execute(
                text(
                    "DELETE FROM request_limits WHERE window_start < :cutoff LIMIT 100"
                ),
                {"cutoff": window - timedelta(minutes=2)},
            )
            statement = insert(request_limits).values(
                scope_digest=digest, window_start=window, request_count=1
            )
            connection.execute(
                statement.on_duplicate_key_update(
                    request_count=func.least(
                        request_limits.c.request_count + 1, limit + 1
                    )
                )
            )
            count = connection.scalar(
                select(request_limits.c.request_count).where(
                    request_limits.c.scope_digest == digest,
                    request_limits.c.window_start == window,
                )
            )
            return count <= limit, 60 - now.second
