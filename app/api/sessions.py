"""本人会话创建、回读与受保护的POST SSE消息入口。"""

from flask import g, request

from app.api.ai_apps import body, key, pagination
from app.api.auth import COOKIE
from app.api.http import success
from app.api.streaming import stream_response
from app.services.ai_contracts import AI_CONFIGURE, AI_USE, bad, identifier
from app.services.feedback import FeedbackService
from app.services.session_stream import SessionStreamService
from app.services.sessions import SessionService

SESSION_POLICIES = {
    (endpoint, method): AI_USE
    for endpoint, methods in (
        ("list_private_sessions", ("GET", "HEAD")),
        ("create_private_session", ("POST",)),
        ("read_private_session", ("GET", "HEAD")),
        ("send_private_message", ("POST",)),
        ("issue_unit_practice", ("POST",)),
        ("read_history_citation", ("GET", "HEAD")),
        ("put_message_feedback", ("PUT",)),
    )
    for method in methods
}

SESSION_POLICIES.update(
    {("list_teaching_feedback", method): AI_CONFIGURE for method in ("GET", "HEAD")}
)
SESSION_POLICIES[("handle_teaching_feedback", "PATCH")] = AI_CONFIGURE


def install_sessions(app, ai_apps, retrieval, tool_connectors=None, unit_practice=None):
    service = SessionService(ai_apps, retrieval, tool_connectors, unit_practice)
    app.extensions["private_sessions"] = service
    feedback = FeedbackService(service)
    app.extensions["teaching_feedback"] = feedback

    @app.after_request
    def session_no_store(response):
        if request.endpoint in {endpoint for endpoint, _ in SESSION_POLICIES}:
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/v1/sessions")
    def list_private_sessions():
        return success(
            service.list(g.identity, request.cookies.get(COOKIE), *pagination())
        )

    @app.post("/api/v1/sessions")
    def create_private_session():
        row, replayed = service.create(
            g.identity,
            request.cookies.get(COOKIE),
            body({"assistant_id", "mode"}),
            key(),
        )
        return success(row | {"replayed": replayed}), 200 if replayed else 201

    @app.post("/api/v1/sessions/<session_id>/messages")
    def send_private_message(session_id):
        stream = SessionStreamService(service).start(
            g.identity,
            request.cookies.get(COOKIE),
            identifier(session_id),
            key(),
            body(),
            g.request_id,
        )
        return stream_response(stream)

    @app.post("/api/v1/sessions/<session_id>/unit-practice")
    def issue_unit_practice(session_id):
        body(set())
        return success(
            service.issue_practice(
                g.identity, request.cookies.get(COOKIE), identifier(session_id), key()
            )
        )

    @app.get("/api/v1/sessions/<session_id>")
    def read_private_session(session_id):
        return success(
            service.read(
                g.identity,
                request.cookies.get(COOKIE),
                identifier(session_id),
                *pagination(),
            )
        )

    @app.get("/api/v1/sessions/<session_id>/messages/<message_id>/citations/<ordinal>")
    def read_history_citation(session_id, message_id, ordinal):
        if request.args or ordinal not in ("1", "2", "3", "4"):
            raise bad()
        return success(
            feedback.citation(
                g.identity,
                request.cookies.get(COOKIE),
                identifier(session_id),
                identifier(message_id),
                int(ordinal),
            )
        )

    @app.put("/api/v1/sessions/<session_id>/messages/<message_id>/feedback")
    def put_message_feedback(session_id, message_id):
        return success(
            feedback.put(
                g.identity,
                request.cookies.get(COOKIE),
                identifier(session_id),
                identifier(message_id),
                body(),
            )
        )

    @app.get("/api/v1/teaching-feedback")
    def list_teaching_feedback():
        page, size = pagination(("status",))
        return success(
            feedback.list(
                g.identity,
                request.cookies.get(COOKIE),
                request.args.get("status", "pending"),
                page,
                size,
            )
        )

    @app.patch("/api/v1/teaching-feedback/<feedback_id>")
    def handle_teaching_feedback(feedback_id):
        return success(
            feedback.handle(
                g.identity, request.cookies.get(COOKIE), identifier(feedback_id), body()
            )
        )
