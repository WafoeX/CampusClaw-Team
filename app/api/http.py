from time import monotonic
from uuid import uuid4

from flask import g, jsonify, request
from werkzeug.exceptions import HTTPException

from app.observability import log_event, utc_time
from app.services.access import AccessDenied, authorize

PUBLIC_PROBES = {"live": "/live", "health": "/health"}


def success(data):
    return jsonify(code=0, message="成功", data=data, request_id=g.request_id)


def install_http(app, *, version, health, resolve_identity, policies):
    @app.before_request
    def prepare_request():
        g.request_id = uuid4().hex
        g.started_at = monotonic()
        if request.routing_exception is not None:
            return None
        key = (request.endpoint, request.method)
        if request.method in {
            "GET",
            "HEAD",
        } and request.url_rule.rule == PUBLIC_PROBES.get(request.endpoint):
            return None
        permission = policies.get(key)
        if not permission:
            raise AccessDenied(403, 1200, "当前账号无此操作权限")
        g.identity = authorize(resolve_identity, permission)
        if health.sample()[0] != 200:
            raise AccessDenied(503, 1500, "依赖服务暂不可用，请稍后重试")

    @app.get("/live", provide_automatic_options=False)
    def live():
        return jsonify(status="alive", request_id=g.request_id)

    @app.get("/health", endpoint="health", provide_automatic_options=False)
    def health_route():
        http_status, status, dependencies = health.sample()
        return jsonify(
            status=status,
            version=version,
            time=utc_time(),
            dependencies=dependencies,
            request_id=g.request_id,
        ), http_status

    @app.errorhandler(AccessDenied)
    def refused(error):
        return jsonify(
            code=error.code, message=error.message, data=None, request_id=g.request_id
        ), error.status

    @app.errorhandler(HTTPException)
    def http_error(error):
        if error.code == 404:
            return refused(AccessDenied(404, 1300, "资源不存在或不可访问"))
        response = error.get_response()
        status = "method_not_allowed" if error.code == 405 else "request_failed"
        response.set_data(
            app.json.dumps({"status": status, "request_id": g.request_id})
        )
        response.mimetype = "application/json"
        return response

    @app.errorhandler(Exception)
    def unexpected_error(_error):
        return jsonify(status="internal_error", request_id=g.request_id), 500

    @app.after_request
    def finish_request(response):
        response.headers["X-Request-ID"] = g.request_id
        if request.endpoint in PUBLIC_PROBES:
            response.headers["Cache-Control"] = "no-store"
        log_event(
            "http",
            version,
            level="ERROR" if response.status_code >= 500 else "INFO",
            request_id=g.request_id,
            status=response.status_code,
            duration_ms=round((monotonic() - g.started_at) * 1000, 2),
        )
        return response
