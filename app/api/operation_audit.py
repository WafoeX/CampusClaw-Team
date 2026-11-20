from datetime import datetime, timedelta
from time import monotonic

from flask import g, request

from app.api.ai_apps import pagination
from app.api.auth import COOKIE
from app.api.http import success
from app.api.materials import _query
from app.observability import log_event
from app.services.ai_contracts import AI_CONFIGURE, bad, identifier

AUDIT_POLICIES = {
    (endpoint, method): AI_CONFIGURE
    for endpoint in ("list_operation_audit", "read_operation_audit")
    for method in ("GET", "HEAD")
}

CONFIGURATION_ENDPOINTS = {
    "create_skill": ("configuration_create", "skill"),
    "update_skill": ("configuration_update", "skill"),
    "delete_skill": ("configuration_delete", "skill"),
    "create_templates": ("configuration_create", "template"),
    "update_templates": ("configuration_update", "template"),
    "delete_ai_template": ("configuration_delete", "template"),
    "create_assistants": ("configuration_create", "assistant"),
    "update_assistants": ("configuration_update", "assistant"),
}


def denied_configuration(audit, version, origin):
    event = CONFIGURATION_ENDPOINTS.get(request.endpoint)
    actor = g.get("actor")
    if (
        actor is not None
        and actor.role == "student"
        and event is not None
        and request.headers.get("Origin") == origin
        and request.headers.get("X-CampusClaw-Request") == "same-origin"
    ):
        if not audit.denied(
            actor,
            g.request_id,
            *event,
            round((monotonic() - g.started_at) * 1000),
        ):
            log_event(
                "operation_audit",
                version,
                level="ERROR",
                request_id=g.request_id,
                event="store_unavailable",
            )


def install_operation_audit(app, audit):
    @app.after_request
    def operation_audit_no_cache(response):
        if (request.endpoint, request.method) in AUDIT_POLICIES:
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/v1/operation-audits")
    def list_operation_audit():
        page, size = pagination(("actor_id", "skill_id", "job_id", "end", "days"))
        filters = {
            name: identifier(request.args[name])
            for name in ("actor_id", "skill_id")
            if name in request.args
        }
        job_id = (
            identifier(request.args["job_id"]) if "job_id" in request.args else None
        )
        end = request.args.get("end")
        if end is not None:
            try:
                end = datetime.strptime(end, "%Y-%m-%dT%H:%M:%SZ")
                now = audit.ai.clock()
                if not now - timedelta(days=90) < end <= now:
                    raise ValueError
            except ValueError:
                raise bad("请使用最近 90 天内的 UTC 时间") from None
        days = request.args.get("days", "7")
        if days not in {"1", "2", "3", "4", "5", "6", "7"}:
            raise bad("审计查询窗口须为 1 至 7 天")
        return success(
            audit.list(
                g.identity,
                request.cookies.get(COOKIE),
                page,
                size,
                end,
                int(days),
                filters,
                job_id,
            )
        )

    @app.get("/api/v1/operation-audits/<event_id>")
    def read_operation_audit(event_id):
        _query()
        return success(
            audit.read(
                g.identity,
                request.cookies.get(COOKIE),
                identifier(event_id),
            )
        )
