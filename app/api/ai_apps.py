"""班级应用、模板和助手API；默认拒绝、同源防护由统一入口执行。"""

import json

from flask import g, request
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

from app.api.auth import COOKIE
from app.api.http import success
from app.api.materials import REQUEST_KEY, _positive, _query
from app.services.ai_contracts import AI_CONFIGURE, AI_USE, bad, identifier

AI_POLICIES = {
    (endpoint, method): permission
    for endpoint, methods, permission in (
        ("ai_catalogue", ("GET", "HEAD"), AI_USE),
        ("list_ai_runs", ("GET", "HEAD"), AI_USE),
        ("read_ai_run", ("GET", "HEAD"), AI_USE),
        ("run_ai_app", ("POST",), AI_USE),
        ("preview_ai_template", ("POST",), AI_USE),
        *(
            (f"list_{kind}", ("GET", "HEAD"), AI_USE)
            for kind in ("templates", "assistants")
        ),
        *(
            (f"read_{kind}", ("GET", "HEAD"), AI_USE)
            for kind in ("templates", "assistants")
        ),
        *(
            (f"create_{kind}", ("POST",), AI_CONFIGURE)
            for kind in ("templates", "assistants")
        ),
        *(
            (f"update_{kind}", ("PATCH",), AI_CONFIGURE)
            for kind in ("templates", "assistants")
        ),
        ("delete_ai_template", ("DELETE",), AI_CONFIGURE),
    )
    for method in methods
}


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def body(keys=None):
    request.max_content_length = 65536
    try:
        if request.args or not request.is_json:
            raise ValueError
        value = json.loads(request.get_data(), object_pairs_hook=unique_keys)
        if not isinstance(value, dict) or (
            keys is not None and value.keys() != set(keys)
        ):
            raise ValueError
        return value
    except (ValueError, UnicodeError, BadRequest, RequestEntityTooLarge):
        raise bad() from None


def key():
    value = request.headers.get("Idempotency-Key", "")
    if not REQUEST_KEY.fullmatch(value):
        raise bad("请使用有效的幂等标识")
    return value.encode("ascii")


def pagination(allowed=()):
    _query({"page", "page_size", *allowed})
    return _positive("page", 1, 1_000_000), _positive("page_size", 20, 100)


def install_ai_apps(app, service):
    @app.after_request
    def ai_no_cache(response):
        if request.endpoint in {endpoint for endpoint, _ in AI_POLICIES}:
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/v1/ai-apps")
    def ai_catalogue():
        _query()
        return success(service.catalogue(g.identity))

    for segment, kind, plural in (
        ("prompt-templates", "template", "templates"),
        ("assistants", "assistant", "assistants"),
    ):

        def listing(kind=kind):
            return success(
                service.list_configurations(
                    g.identity,
                    kind,
                    *pagination({"app_key"} if kind == "template" else ()),
                    app_key=request.args.get("app_key"),
                )
            )

        def reading(resource_id, kind=kind):
            _query()
            return success(
                service.read_configuration(
                    g.identity,
                    request.cookies.get(COOKIE),
                    kind,
                    identifier(resource_id),
                )
            )

        def creating(kind=kind):
            request_key = key()
            result = service.save_configuration(
                g.identity, request.cookies.get(COOKIE), kind, body(), key=request_key
            )
            return success(result), 201

        def updating(resource_id, kind=kind):
            return success(
                service.save_configuration(
                    g.identity,
                    request.cookies.get(COOKIE),
                    kind,
                    body(),
                    resource_id=identifier(resource_id),
                )
            )

        for suffix, endpoint, method, handler in (
            ("", f"list_{plural}", "GET", listing),
            ("/<resource_id>", f"read_{plural}", "GET", reading),
            ("", f"create_{plural}", "POST", creating),
            ("/<resource_id>", f"update_{plural}", "PATCH", updating),
        ):
            app.add_url_rule(
                "/api/v1/" + segment + suffix,
                endpoint=endpoint,
                view_func=handler,
                methods=[method],
            )

    @app.delete("/api/v1/prompt-templates/<resource_id>")
    def delete_ai_template(resource_id):
        payload = body({"revision"})
        return success(
            service.delete_template(
                g.identity,
                request.cookies.get(COOKIE),
                identifier(resource_id),
                payload["revision"],
            )
        )

    @app.post("/api/v1/prompt-templates/<resource_id>/previews")
    def preview_ai_template(resource_id):
        payload = body({"revision", "variables"})
        return success(
            service.preview(
                g.identity,
                request.cookies.get(COOKIE),
                identifier(resource_id),
                payload["revision"],
                payload["variables"],
            )
        )

    @app.post("/api/v1/ai-apps/<app_key>/runs")
    def run_ai_app(app_key):
        request_key = key()
        payload = body({"template_id", "revision", "variables"})
        result = service.run(
            g.identity,
            request.cookies.get(COOKIE),
            app_key,
            request_key,
            identifier(payload["template_id"]),
            payload["revision"],
            payload["variables"],
        )
        return success(result | {"run_id": result["record"]["id"]}), 200 if result[
            "replayed"
        ] else 201

    @app.get("/api/v1/runs")
    def list_ai_runs():
        return success(service.list_runs(g.identity, *pagination()))

    @app.get("/api/v1/runs/<run_id>")
    def read_ai_run(run_id):
        _query()
        return success(service.read_run(g.identity, identifier(run_id)))
