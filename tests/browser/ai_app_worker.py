"""仅浏览器隔离夹具使用的应用模型替身；其余装配使用生产代码。"""

import json
import os
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from app import create_app
from app.adapters.ai_repository import AIRepository
from app.adapters.chat_client import ChatProtocolError
from app.adapters.database import DatabaseError, mysql_engine
from app.adapters.index_clients import IndexDependencyError
from app.adapters.model_lease_repository import ModelLeaseRepository
from app.adapters.rate_limit_repository import RateLimitRepository
from app.config import Settings
from app.services.ai_apps import AIApplicationService
from app.services.auth import utc_now
from app.services.model_gate import ModelGate
from app.services.rate_limits import RequestLimiter
from app.services.streaming import LongRequestCapacity


class SyntheticChat:
    def complete(self, messages, deadline, *, before_call=None):
        if before_call:
            before_call()
        data = json.loads(messages[1]["content"])
        return {"text": "浏览器合成建议：" + data["rendered_prompt"]}


def load_worker():
    settings = replace(
        Settings.load(os.environ, Path("app/BUILD_VERSION")),
        ai_data_expires_at=utc_now() + timedelta(days=30),
    )
    assert settings.mysql_database.startswith("campusclaw_test_")
    engine = mysql_engine(
        host=settings.mysql_host,
        port=settings.mysql_port,
        database=settings.mysql_database,
        user=settings.mysql_user,
        password=settings.mysql_password,
    )
    limiter = RequestLimiter(RateLimitRepository(engine), DatabaseError)
    service = AIApplicationService(
        AIRepository(engine),
        DatabaseError,
        SyntheticChat(),
        IndexDependencyError,
        ChatProtocolError,
        capacity=LongRequestCapacity(),
        model_guard=ModelGate(ModelLeaseRepository(engine), DatabaseError).hold,
        quota=lambda identity: limiter.check(
            "model-call", identity.subject_id, limit=6
        ),
        expires_at=settings.ai_data_expires_at,
        model_configuration={
            "model": "synthetic-browser-chat",
            "temperature": 0.2,
            "max_output_tokens": 2048,
        },
    )
    app = create_app(settings, ai_apps=service)
    service.capacity = app.extensions["long_request_capacity"]
    return app
