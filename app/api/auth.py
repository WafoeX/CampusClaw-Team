import re
from datetime import UTC
from secrets import token_urlsafe

from flask import g, make_response, render_template, request
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

from app.api.http import success
from app.services.access import AccessDenied, Identity

COOKIE = "__Host-campusclaw_session"
COOKIE_OPTIONS = {"secure": True, "httponly": True, "samesite": "Strict", "path": "/"}
LOGIN_NAME = re.compile(r"[a-zA-Z0-9_-]{1,64}")
DETAIL_PATH = re.compile(r"/materials/[a-f0-9-]{36}")
AUTH_POLICIES = {
    ("current_session", "GET"): "session",
    ("current_session", "HEAD"): "session",
    ("logout", "DELETE"): "session",
}
AUTH_PUBLIC_ROUTES = {
    ("login_page", "/login", "GET"),
    ("login_page", "/login", "HEAD"),
    ("login", "/api/v1/auth/sessions", "POST"),
}


def resolve_session(auth):
    actor = auth.current(request.cookies.get(COOKIE))
    if actor is None:
        return None
    g.actor = actor
    return Identity(actor.id, actor.class_id, frozenset({"session"}))


def _login_input():
    request.max_content_length = 2048
    try:
        payload = request.get_json() if request.is_json and not request.args else None
        if not isinstance(payload, dict) or payload.keys() != {
            "login_name",
            "password",
        }:
            raise ValueError
        name, password = payload["login_name"], payload["password"]
        if (
            not isinstance(name, str)
            or not LOGIN_NAME.fullmatch(name)
            or not isinstance(password, str)
            or not 1 <= len(password.encode("utf-8")) <= 128
        ):
            raise ValueError
    except (BadRequest, RequestEntityTooLarge, ValueError):
        raise AccessDenied(400, 1000, "请检查登录名与口令格式") from None
    return name.lower(), password


def _expires_at(value):
    return value.replace(tzinfo=UTC).isoformat()


def _return_path(app, path):
    registered = {
        rule.rule for rule in app.url_map.iter_rules() if "GET" in rule.methods
    }
    if path == "/console" and "/console" in registered:
        return path
    if DETAIL_PATH.fullmatch(path) and "/materials/<material_id>" in registered:
        return path
    return "/materials" if "/materials" in registered else "/login"


def install_auth(app, auth, origin):
    @app.before_request
    def verify_write_origin():
        if request.routing_exception is not None or request.method in {
            "GET",
            "HEAD",
            "OPTIONS",
        }:
            return
        if (
            request.headers.get("Origin") != origin
            or request.headers.get("X-CampusClaw-Request") != "same-origin"
        ):
            raise AccessDenied(403, 1200, "请从本系统页面重新操作")

    @app.after_request
    def auth_response(response):
        if request.endpoint in {"login_page", "login", "current_session", "logout"}:
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/login")
    def login_page():
        nonce = token_urlsafe(24)
        response = make_response(
            render_template(
                "login.html",
                nonce=nonce,
                destination=_return_path(app, request.args.get("next", "")),
            )
        )
        response.headers["Content-Security-Policy"] = (
            f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; "
            "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
        )
        return response

    @app.post("/api/v1/auth/sessions")
    def login():
        cookie, expires = auth.login(*_login_input())
        response = success({"expires_at": _expires_at(expires)})
        response.set_cookie(COOKIE, cookie, **COOKIE_OPTIONS)
        return response

    @app.get("/api/v1/auth/sessions/current")
    def current_session():
        actor = g.actor
        return success(
            {
                "id": actor.id,
                "login_name": actor.login_name,
                "class_id": actor.class_id,
                "class_name": actor.class_name,
                "role": actor.role,
                "expires_at": _expires_at(actor.expires_at),
            }
        )

    @app.delete("/api/v1/auth/sessions/current")
    def logout():
        auth.logout(g.identity.subject_id, request.cookies.get(COOKIE))
        response = success({"revoked": True})
        response.delete_cookie(COOKIE, **COOKIE_OPTIONS)
        return response
