from flask import request

from app.api.ai_apps import body
from app.api.auth import COOKIE, CSRF_ISSUER
from app.api.http import success
from app.api.operation_audit import CONFIGURATION_ENDPOINTS
from app.services.ai_contracts import bad

CSRF_HEADER = "X-CampusClaw-CSRF"
CSRF_POLICIES = {(CSRF_ISSUER, "POST"): "session"}


def install_csrf(app, auth):
    @app.before_request
    def consume_configuration_csrf():
        if request.endpoint in CONFIGURATION_ENDPOINTS:
            auth.consume_csrf(
                request.cookies.get(COOKIE),
                request.headers.get(CSRF_HEADER),
                request.endpoint,
            )

    @app.after_request
    def csrf_no_store(response):
        if request.endpoint == CSRF_ISSUER:
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/api/v1/auth/csrf-tokens", endpoint=CSRF_ISSUER)
    def issue():
        action = body({"action"})["action"]
        if not isinstance(action, str) or action not in CONFIGURATION_ENDPOINTS:
            raise bad()
        token = auth.issue_csrf(request.cookies.get(COOKIE), action)
        return success({"token": token})
