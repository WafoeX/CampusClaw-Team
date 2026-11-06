from flask import g, request

from app.api.auth import COOKIE
from app.api.http import success
from app.api.retrieval import query_input
from app.services.materials import READ_MATERIALS

ANSWER_POLICIES = {("answer_materials", "POST"): READ_MATERIALS}


def install_answers(app, service):
    @app.post("/api/v1/material-answers")
    def answer_materials():
        return success(
            service.answer(
                g.identity,
                request.cookies.get(COOKIE),
                *query_input("question", "hybrid"),
            )
        )

    @app.after_request
    def answer_cache(response):
        if request.endpoint == "answer_materials":
            response.headers["Cache-Control"] = "no-store"
        return response
