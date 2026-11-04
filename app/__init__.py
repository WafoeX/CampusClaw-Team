import os
from pathlib import Path

from flask import Flask

from app.adapters.probes import check_mysql, check_qdrant
from app.api.http import install_http
from app.config import Settings
from app.services.health import HealthService

VERSION_FILE = Path(__file__).with_name("BUILD_VERSION")


def create_app(
    settings=None, *, health=None, resolve_identity=None, policies=None, draining=None
):
    if settings is None:
        settings = Settings.load(os.environ, VERSION_FILE)
    if health is None:
        health = HealthService(
            lambda: check_mysql(settings),
            lambda: check_qdrant(settings),
            draining or (lambda: False),
        )
    app = Flask(__name__, static_folder=None)
    app.config["PROVIDE_AUTOMATIC_OPTIONS"] = False
    install_http(
        app,
        version=settings.version,
        health=health,
        resolve_identity=resolve_identity or (lambda: None),
        policies=dict(policies or {}),
    )
    return app
