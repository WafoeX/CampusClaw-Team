import os
from io import BytesIO
from pathlib import Path

from flask import Flask, Request, g, has_request_context
from werkzeug.security import check_password_hash, generate_password_hash

from app.adapters.ai_repository import AIRepository
from app.adapters.auth_repository import AuthRepository
from app.adapters.chapter_repository import ChapterRepository
from app.adapters.chat_client import ChatClient, ChatProtocolError
from app.adapters.database import DatabaseError, mysql_engine
from app.adapters.index_clients import (
    EmbeddingClient,
    IndexDependencyError,
    QdrantIndexClient,
)
from app.adapters.index_repository import IndexRepository
from app.adapters.material_repository import MaterialRepository
from app.adapters.model_lease_repository import ModelLeaseRepository
from app.adapters.probes import check_mysql, check_qdrant
from app.adapters.rate_limit_repository import RateLimitRepository
from app.adapters.retrieval_repository import RetrievalRepository
from app.adapters.teaching_repository import TeachingRepository
from app.api.ai_apps import AI_POLICIES, install_ai_apps
from app.api.answers import ANSWER_POLICIES, install_answers
from app.api.auth import (
    AUTH_POLICIES,
    AUTH_PUBLIC_ROUTES,
    install_auth,
    resolve_session,
)
from app.api.chapters import CHAPTER_POLICIES, install_chapters
from app.api.http import install_http
from app.api.index_builds import INDEX_POLICIES, install_index_builds
from app.api.material_pages import PAGE_POLICIES, install_material_pages, login_redirect
from app.api.materials import MATERIAL_POLICIES, install_materials
from app.api.openapi import DOC_POLICIES, install_openapi
from app.api.retrieval import RETRIEVAL_POLICIES, install_retrieval
from app.api.sessions import SESSION_POLICIES, install_sessions
from app.api.skills import SKILL_POLICIES, install_skills
from app.api.teaching import TEACHING_POLICIES, install_teaching
from app.api.teaching_pages import TEACHING_PAGE_POLICIES, install_teaching_pages
from app.config import Settings
from app.observability import log_event
from app.services.ai_apps import AIApplicationService
from app.services.answers import AnswerService
from app.services.auth import AuthService
from app.services.chapters import ChapterService
from app.services.health import HealthService
from app.services.indexing import IndexService
from app.services.materials import MaterialService
from app.services.model_gate import ModelGate
from app.services.rate_limits import RequestLimiter
from app.services.retrieval import RetrievalService
from app.services.streaming import LongRequestCapacity
from app.services.teaching import TeachingService

VERSION_FILE = Path(__file__).with_name("BUILD_VERSION")


class CampusRequest(Request):
    def _get_file_stream(self, *args, **kwargs):
        # 资料上传的请求体大小由路由在解析前限制。
        return BytesIO()


def create_app(
    settings=None,
    *,
    health=None,
    resolve_identity=None,
    policies=None,
    public_routes=(),
    draining=None,
    auth=None,
    materials=None,
    limiter=None,
    chapters=None,
    indexing=None,
    retrieval=None,
    answers=None,
    ai_apps=None,
    teaching=None,
):
    if settings is None:
        settings = Settings.load(os.environ, VERSION_FILE)
    if draining is None:
        draining = getattr(health, "draining", None) or (lambda: False)
    if health is None:
        health = HealthService(
            lambda: check_mysql(settings),
            lambda: check_qdrant(settings),
            draining,
        )
    app = Flask(__name__, static_folder=None)
    app.extensions["long_request_capacity"] = LongRequestCapacity(draining=draining)
    app.request_class = CampusRequest
    app.config["PROVIDE_AUTOMATIC_OPTIONS"] = False
    origin = settings.public_origin
    if origin is not None:
        if (
            auth is None
            or materials is None
            or limiter is None
            or chapters is None
            or (settings.embedding is not None and indexing is None)
            or retrieval is None
            or answers is None
            or ai_apps is None
            or teaching is None
        ):
            engine = mysql_engine(
                host=settings.mysql_host,
                port=settings.mysql_port,
                database=settings.mysql_database,
                user=settings.mysql_user,
                password=settings.mysql_password,
            )
        if auth is None:
            auth = AuthService(
                AuthRepository(engine),
                check_password_hash,
                generate_password_hash("unused-login-placeholder", method="scrypt"),
                DatabaseError,
            )
        if materials is None:
            materials = MaterialService(MaterialRepository(engine), DatabaseError)
        if limiter is None:
            limiter = RequestLimiter(RateLimitRepository(engine), DatabaseError)
        if chapters is None:
            chapters = ChapterService(ChapterRepository(engine), DatabaseError)
        if teaching is None:
            teaching = TeachingService(TeachingRepository(engine), DatabaseError)

        def model_event(**details):
            log_event(
                "model",
                settings.version,
                request_id=g.request_id if has_request_context() else None,
                **details,
            )

        if indexing is None and settings.embedding is not None:
            indexing = IndexService(
                IndexRepository(engine),
                DatabaseError,
                EmbeddingClient(settings.embedding, on_result=model_event),
                QdrantIndexClient(
                    settings.qdrant_url, settings.qdrant_api_key, settings.embedding
                ),
                IndexDependencyError,
                settings.embedding.version,
                quota=lambda identity: limiter.check(
                    "model-call", identity.subject_id, limit=6
                ),
                model_guard=ModelGate(ModelLeaseRepository(engine), DatabaseError).hold,
            )
        if retrieval is None:
            config = settings.embedding
            retrieval = RetrievalService(
                RetrievalRepository(engine),
                DatabaseError,
                EmbeddingClient(config, on_result=model_event)
                if config is not None
                else None,
                QdrantIndexClient(settings.qdrant_url, settings.qdrant_api_key, config)
                if config is not None
                else None,
                IndexDependencyError,
                auth.current,
                settings.retrieval_min_score,
                quota=lambda identity: limiter.check(
                    "model-call", identity.subject_id, limit=6
                ),
                model_guard=ModelGate(ModelLeaseRepository(engine), DatabaseError).hold,
            )
        if answers is None:
            answers = AnswerService(
                retrieval,
                ChatClient(settings.chat, on_result=model_event)
                if settings.chat
                else None,
                IndexDependencyError,
                ChatProtocolError,
                quota=lambda identity: limiter.check(
                    "model-call", identity.subject_id, limit=6
                ),
                model_guard=ModelGate(ModelLeaseRepository(engine), DatabaseError).hold,
                on_result=model_event,
            )
        if ai_apps is None:
            ai_apps = AIApplicationService(
                AIRepository(engine),
                DatabaseError,
                ChatClient(settings.chat, on_result=model_event)
                if settings.chat
                else None,
                IndexDependencyError,
                ChatProtocolError,
                capacity=app.extensions["long_request_capacity"],
                model_guard=ModelGate(ModelLeaseRepository(engine), DatabaseError).hold,
                quota=lambda identity: limiter.check(
                    "model-call", identity.subject_id, limit=6
                ),
                expires_at=settings.ai_data_expires_at,
                model_configuration=(
                    {
                        "model": settings.chat.model,
                        "model_config": settings.chat.version,
                        "temperature": settings.chat.temperature,
                        "max_output_tokens": settings.chat.max_output_tokens,
                    }
                    if settings.chat
                    else {}
                ),
            )
        resolve_identity = resolve_identity or (lambda: resolve_session(auth))
        policies = {
            **(policies or {}),
            **AUTH_POLICIES,
            **MATERIAL_POLICIES,
            **CHAPTER_POLICIES,
            **PAGE_POLICIES,
            **(INDEX_POLICIES if indexing is not None else {}),
            **RETRIEVAL_POLICIES,
            **ANSWER_POLICIES,
            **AI_POLICIES,
            **SKILL_POLICIES,
            **SESSION_POLICIES,
            **DOC_POLICIES,
            **TEACHING_POLICIES,
            **TEACHING_PAGE_POLICIES,
        }
        public_routes = (*public_routes, *AUTH_PUBLIC_ROUTES)
    install_http(
        app,
        version=settings.version,
        health=health,
        resolve_identity=resolve_identity or (lambda: None),
        policies=dict(policies or {}),
        public_routes=frozenset(public_routes),
        draining=draining,
        page_login=login_redirect if origin is not None else None,
    )
    if origin is not None:
        install_auth(app, auth, origin, limiter)
        install_materials(app, materials)
        if indexing is not None:
            install_index_builds(app, indexing)
        install_chapters(app, chapters)
        install_retrieval(app, retrieval)
        install_answers(app, answers)
        install_ai_apps(app, ai_apps)
        install_skills(app, ai_apps)
        install_sessions(app, ai_apps, retrieval)
        install_material_pages(app)
        install_openapi(app)
        install_teaching(app, teaching)
        install_teaching_pages(app)
    return app
