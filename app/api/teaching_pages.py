"""题库和测验页面的服务端入口。"""

from secrets import token_urlsafe

from flask import g, make_response, render_template

from app.api.materials import material_id
from app.services.access import AccessDenied
from app.services.materials import READ_MATERIALS
from app.services.teaching import TEACHING_WRITE

TEACHING_PAGE_POLICIES = {
    (endpoint, method): permission
    for endpoint, permission in (
        ("questions_page", TEACHING_WRITE),
        ("quizzes_page", READ_MATERIALS),
        ("quiz_page", READ_MATERIALS),
        ("mistakes_page", READ_MATERIALS),
        ("dashboard_page", TEACHING_WRITE),
    )
    for method in ("GET", "HEAD")
}


def install_teaching_pages(app, *, generation_enabled=False):
    def render(view, target=None):
        nonce = token_urlsafe(24)
        response = make_response(
            render_template(
                "teaching.html",
                view=view,
                target=target,
                actor=g.actor,
                nonce=nonce,
                generation_enabled=generation_enabled,
            )
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; "
            "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
        )
        return response

    @app.get("/console/questions")
    def questions_page():
        return render("questions")

    @app.get("/quizzes")
    def quizzes_page():
        return render("quizzes")

    @app.get("/quizzes/<value>")
    def quiz_page(value):
        return render("quiz", material_id(value))

    @app.get("/mistakes")
    def mistakes_page():
        if g.actor.role != "student":
            raise AccessDenied(403, 1200, "当前账号无此操作权限")
        return render("mistakes")

    @app.get("/console/dashboard")
    def dashboard_page():
        return render("dashboard")
