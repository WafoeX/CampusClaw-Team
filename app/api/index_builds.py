from flask import g, request
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

from app.api.auth import COOKIE
from app.api.http import success
from app.api.materials import REQUEST_KEY, _json, _query, bad_input, material_id
from app.services.chunking import ChunkConfig
from app.services.materials import WRITE_MATERIALS

INDEX_POLICIES = {
    ("create_index_build", "POST"): WRITE_MATERIALS,
    ("list_index_builds", "GET"): WRITE_MATERIALS,
    ("list_index_builds", "HEAD"): WRITE_MATERIALS,
    ("read_index_build", "GET"): WRITE_MATERIALS,
    ("read_index_build", "HEAD"): WRITE_MATERIALS,
}


def install_index_builds(app, service):
    @app.post("/api/v1/materials/<value>/index-builds")
    def create_index_build(value):
        _query()
        target = material_id(value)
        key = request.headers.get("Idempotency-Key", "")
        if not REQUEST_KEY.fullmatch(key):
            raise bad_input("构建标识格式无效")
        try:
            fields = _json(4096)
        except (BadRequest, RequestEntityTooLarge):
            raise bad_input() from None
        if fields.keys() - {"mode", "window", "overlap"}:
            raise bad_input()
        config = ChunkConfig(**fields)
        result, status = service.run(
            g.identity, request.cookies.get(COOKIE), target, key.encode("ascii"), config
        )
        return success(result), status

    @app.get("/api/v1/materials/<value>/index-builds")
    def list_index_builds(value):
        _query()
        return success(
            service.status(g.identity, request.cookies.get(COOKIE), material_id(value))
        )

    @app.get("/api/v1/materials/<value>/index-builds/<build_id>")
    def read_index_build(value, build_id):
        _query()
        return success(
            service.status(
                g.identity,
                request.cookies.get(COOKIE),
                material_id(value),
                material_id(build_id),
            )
        )
