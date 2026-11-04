import os
from pathlib import Path

from flask import Flask
from werkzeug.security import check_password_hash, generate_password_hash

from app.adapters.auth_repository import AuthRepository
from app.adapters.database import DatabaseError, mysql_engine
from app.adapters.probes import check_mysql, check_qdrant
from app.api.auth import (
    AUTH_POLICIES,
    AUTH_PUBLIC_ROUTES,
    install_auth,
    resolve_session,
)
from app.api.http import install_http
from app.config import Settings
from app.services.auth import AuthService
from app.services.health import HealthService

VERSION_FILE = Path(__file__).with_name("BUILD_VERSION")


def create_app(
    settings=None,
    *,
    health=None,
    resolve_identity=None,
    policies=None,
    public_routes=(),
    draining=None,
    auth=None,
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
    app.config["PROVIDE_AUTOMATIC_OPTIONS"] = False
    origin = settings.public_origin
    if origin is not None:
        if auth is None:
            engine = mysql_engine(
                host=settings.mysql_host,
                port=settings.mysql_port,
                database=settings.mysql_database,
                user=settings.mysql_user,
                password=settings.mysql_password,
            )
            auth = AuthService(
                AuthRepository(engine),
                check_password_hash,
                generate_password_hash("unused-login-placeholder", method="scrypt"),
                DatabaseError,
            )
        resolve_identity = resolve_identity or (lambda: resolve_session(auth))
        policies = {**(policies or {}), **AUTH_POLICIES}
        public_routes = (*public_routes, *AUTH_PUBLIC_ROUTES)
    install_http(
        app,
        version=settings.version,
        health=health,
        resolve_identity=resolve_identity or (lambda: None),
        policies=dict(policies or {}),
        public_routes=frozenset(public_routes),
        draining=draining,
    )
    if origin is not None:
        install_auth(app, auth, origin)
    return app
