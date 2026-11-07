from flask import g, request
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

from app.api.auth import COOKIE
from app.api.http import success
from app.api.materials import _json, _query, bad_input, material_id
from app.services.materials import READ_MATERIALS

RETRIEVAL_POLICIES = {
    ("search_materials", "POST"): READ_MATERIALS,
    ("open_material_citation", "GET"): READ_MATERIALS,
    ("open_material_citation", "HEAD"): READ_MATERIALS,
}


def query_input(name="query", default_mode="keyword"):
    _query()
    try:
        fields = _json(32768)
    except (BadRequest, RequestEntityTooLarge):
        raise bad_input() from None
    if fields.keys() - {name, "mode", "chapter_scope"} or name not in fields:
        raise bad_input()
    query = fields[name]
    mode = fields.get("mode", default_mode)
    if (
        not isinstance(query, str)
        or not 1 <= len(query.strip()) <= 4000
        or "\0" in query
        or mode not in ("keyword", "vector", "hybrid")
    ):
        raise bad_input()
    try:
        query.encode("utf-8")
    except UnicodeError:
        raise bad_input() from None
    scope = fields.get("chapter_scope")
    if "chapter_scope" in fields:
        if not isinstance(scope, str) or not scope:
            raise bad_input()
        if scope != "uncategorized":
            material_id(scope)
    return query.strip(), mode, scope


def install_retrieval(app, service):
    @app.post("/api/v1/searches")
    def search_materials():
        return success(
            service.search(g.identity, request.cookies.get(COOKIE), *query_input())
        )

    @app.get("/api/v1/materials/<value>/citations/<chunk_id>")
    def open_material_citation(value, chunk_id):
        _query(("source_version", "index_version"))
        versions = []
        for name in ("source_version", "index_version"):
            raw = request.args.get(name, "")
            if (
                not raw.isascii()
                or not raw.isdecimal()
                or len(raw) > 10
                or not 1 <= int(raw) <= 2**31 - 1
            ):
                raise bad_input("出处版本无效")
            versions.append(int(raw))
        return success(
            service.open_citation(
                g.identity,
                request.cookies.get(COOKIE),
                material_id(value),
                material_id(chunk_id),
                *versions,
            )
        )

    @app.after_request
    def retrieval_cache(response):
        if request.endpoint in {"search_materials", "open_material_citation"}:
            response.headers["Cache-Control"] = "no-store"
        return response
