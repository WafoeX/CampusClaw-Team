import os
from io import BytesIO
from pathlib import Path

from flask import Flask, Request
from werkzeug.security import check_password_hash, generate_password_hash

from app.adapters.auth_repository import AuthRepository
from app.adapters.database import DatabaseError, mysql_engine
from app.adapters.material_repository import MaterialRepository
from app.adapters.probes import check_mysql, check_qdrant
from app.adapters.rate_limit_repository import RateLimitRepository
from app.api.auth import (
    AUTH_POLICIES,
    AUTH_PUBLIC_ROUTES,
    install_auth,
    resolve_session,
)
from app.api.http import install_http
from app.api.material_pages import PAGE_POLICIES, install_material_pages, login_redirect
from app.api.materials import MATERIAL_POLICIES, install_materials
from app.config import Settings
from app.services.auth import AuthService
from app.services.health import HealthService
from app.services.materials import MaterialService
from app.services.rate_limits import RequestLimiter

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
    app.request_class = CampusRequest
    app.config["PROVIDE_AUTOMATIC_OPTIONS"] = False
    origin = settings.public_origin
    if origin is not None:
        if auth is None or materials is None or limiter is None:
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
        resolve_identity = resolve_identity or (lambda: resolve_session(auth))
        policies = {
            **(policies or {}),
            **AUTH_POLICIES,
            **MATERIAL_POLICIES,
            **PAGE_POLICIES,
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
        install_material_pages(app)
    return app
