from secrets import token_urlsafe

from flask import g, make_response, redirect, render_template, request, url_for

from app.api.materials import MATERIAL_ID
from app.api.materials import material_id as validate_id
from app.services.ai_contracts import AI_CONFIGURE, AI_USE
from app.services.materials import READ_MATERIALS, WRITE_MATERIALS

PAGE_PERMISSIONS = {
    "materials_page": READ_MATERIALS,
    "material_page": READ_MATERIALS,
    "chapters_page": READ_MATERIALS,
    "console_page": WRITE_MATERIALS,
    "search_page": READ_MATERIALS,
    "ask_page": READ_MATERIALS,
    "apps_page": AI_USE,
    "runs_page": AI_USE,
    "sessions_page": AI_USE,
    "session_page": AI_USE,
    "run_page": AI_USE,
    "templates_page": AI_CONFIGURE,
    "skills_page": AI_CONFIGURE,
    "feedback_page": AI_CONFIGURE,
}
PAGE_POLICIES = {
    (endpoint, method): permission
    for endpoint, permission in PAGE_PERMISSIONS.items()
    for method in ("GET", "HEAD")
}


def login_redirect():
    if request.endpoint not in PAGE_PERMISSIONS:
        return None
    target = request.path
    if request.endpoint == "material_page" and not MATERIAL_ID.fullmatch(
        request.view_args["material_id"]
    ):
        target = "/materials"
    response = redirect(url_for("login_page", next=target), code=303)
    response.headers["Cache-Control"] = "no-store"
    return response


def install_material_pages(app):
    def render(view, target=None):
        nonce = token_urlsafe(24)
        response = make_response(
            render_template(
                "materials.html",
                nonce=nonce,
                view=view,
                target=target,
                actor=g.actor,
                indexing_enabled="create_index_build" in app.view_functions,
            )
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; "
            "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
        )
        return response

    @app.get("/console/feedback")
    def feedback_page():
        return render("feedback")

    @app.get("/console/skills")
    def skills_page():
        return render("skills")

    @app.get("/apps")
    def apps_page():
        return render("apps")

    @app.get("/sessions")
    def sessions_page():
        return render("sessions")

    @app.get("/sessions/<session_id>")
    def session_page(session_id):
        return render("sessions", target=validate_id(session_id))

    @app.get("/runs")
    def runs_page():
        return render("runs")

    @app.get("/runs/<run_id>")
    def run_page(run_id):
        return render("runs", target=validate_id(run_id))

    @app.get("/console/templates")
    def templates_page():
        return render("templates")

    @app.get("/materials")
    def materials_page():
        return render("list")

    @app.get("/chapters")
    def chapters_page():
        return render("chapters")

    @app.get("/materials/<material_id>")
    def material_page(material_id):
        return render("detail", target=validate_id(material_id))

    @app.get("/console")
    def console_page():
        return render("console")

    @app.get("/search")
    def search_page():
        return render("search")

    @app.get("/ask")
    def ask_page():
        return render("ask")
