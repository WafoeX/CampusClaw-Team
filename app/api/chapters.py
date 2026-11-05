from flask import g, request
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

from app.api.auth import COOKIE
from app.api.http import success
from app.api.materials import (
    REQUEST_KEY,
    _json,
    _positive,
    _query,
    bad_input,
    material_id,
)
from app.services.materials import READ_MATERIALS, WRITE_MATERIALS

CHAPTER_POLICIES = {
    (endpoint, method): permission
    for endpoint, methods, permission in (
        ("list_chapters", ("GET", "HEAD"), READ_MATERIALS),
        ("read_chapter", ("GET", "HEAD"), READ_MATERIALS),
        ("list_chapter_materials", ("GET", "HEAD"), READ_MATERIALS),
        ("create_chapter", ("POST",), WRITE_MATERIALS),
        ("revise_chapter", ("PATCH",), WRITE_MATERIALS),
        ("delete_chapter", ("DELETE",), WRITE_MATERIALS),
        ("assign_chapter", ("PUT",), WRITE_MATERIALS),
    )
    for method in methods
}


def _payload():
    try:
        return _json(4096)
    except (BadRequest, RequestEntityTooLarge):
        raise bad_input() from None


def _name(value):
    if not isinstance(value, str):
        raise bad_input()
    name = value.strip()
    if not 1 <= len(name) <= 120 or name == "未分类" or "\0" in name:
        raise bad_input("章节名称须为 1 至 120 字符，且不能为未分类")
    try:
        name.encode("utf-8")
    except UnicodeError:
        raise bad_input() from None
    return name


def _order(value):
    if type(value) is not int or not 0 <= value <= 1_000_000:
        raise bad_input("章节排序须为 0 至 1000000 的整数")
    return value


def _revision(value):
    if type(value) is not int or not 1 <= value <= 2**31 - 1:
        raise bad_input("修订号无效")
    return value


def _key():
    value = request.headers.get("Idempotency-Key", "")
    if not REQUEST_KEY.fullmatch(value):
        raise bad_input("请求标识格式无效")
    return value.encode("ascii")


def _chapter_id(value):
    return material_id(value)


def install_chapters(app, service):
    @app.after_request
    def chapter_response(response):
        if (
            request.path == "/api/v1/chapters"
            or request.path.startswith("/api/v1/chapters/")
            or request.path.endswith("/chapter-assignments/current")
        ):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/v1/chapters")
    def list_chapters():
        _query()
        return success(service.list(g.identity))

    @app.get("/api/v1/chapters/<value>")
    def read_chapter(value):
        _query()
        return success(service.read(g.identity, _chapter_id(value)))

    @app.get("/api/v1/chapters/<scope>/materials")
    def list_chapter_materials(scope):
        _query(("page", "page_size"))
        chapter = None if scope == "uncategorized" else _chapter_id(scope)
        return success(
            service.list_materials(
                g.identity,
                chapter,
                _positive("page", 1, 2**31 - 1),
                _positive("page_size", 20, 100),
            )
        )

    @app.post("/api/v1/chapters")
    def create_chapter():
        _query()
        key, fields = _key(), _payload()
        if fields.keys() != {"name", "sort_order"}:
            raise bad_input()
        return success(
            service.create(
                g.identity,
                request.cookies.get(COOKIE),
                key,
                _name(fields["name"]),
                _order(fields["sort_order"]),
            )
        ), 201

    @app.patch("/api/v1/chapters/<value>")
    def revise_chapter(value):
        _query()
        chapter = _chapter_id(value)
        fields = _payload()
        if (
            fields.keys() - {"revision", "name", "sort_order"}
            or len(fields) < 2
            or "revision" not in fields
        ):
            raise bad_input()
        revision = _revision(fields.pop("revision"))
        if "name" in fields:
            fields["name"] = _name(fields["name"])
        if "sort_order" in fields:
            fields["sort_order"] = _order(fields["sort_order"])
        return success(
            service.revise(
                g.identity, request.cookies.get(COOKIE), chapter, revision, fields
            )
        )

    @app.delete("/api/v1/chapters/<value>")
    def delete_chapter(value):
        _query()
        chapter = _chapter_id(value)
        fields = _payload()
        if fields.keys() != {"revision"}:
            raise bad_input()
        return success(
            service.remove(
                g.identity,
                request.cookies.get(COOKIE),
                chapter,
                _revision(fields["revision"]),
            )
        )

    @app.put("/api/v1/materials/<value>/chapter-assignments/current")
    def assign_chapter(value):
        _query()
        material = material_id(value)
        key, fields = _key(), _payload()
        if fields.keys() != {"chapter_id", "revision"}:
            raise bad_input()
        chapter = fields["chapter_id"]
        if chapter is not None:
            if not isinstance(chapter, str):
                raise bad_input()
            chapter = _chapter_id(chapter)
        return success(
            service.assign(
                g.identity,
                request.cookies.get(COOKIE),
                key,
                material,
                chapter,
                _revision(fields["revision"]),
            )
        )
