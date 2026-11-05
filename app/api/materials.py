import re
from io import BytesIO

from flask import g, request, send_file
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

from app.api.auth import COOKIE
from app.api.http import success
from app.services.access import AccessDenied
from app.services.materials import READ_MATERIALS, WRITE_MATERIALS

MATERIAL_ID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
)
REQUEST_KEY = re.compile(r"[a-zA-Z0-9_-]{1,64}")
FORMATS = {".txt": "txt", ".md": "md", ".markdown": "md"}
MATERIAL_LIMIT = 1_048_576
MATERIAL_POLICIES = {
    (endpoint, method): permission
    for endpoint, methods, permission in (
        ("list_materials", ("GET", "HEAD"), READ_MATERIALS),
        ("read_material", ("GET", "HEAD"), READ_MATERIALS),
        ("download_material", ("GET", "HEAD"), READ_MATERIALS),
        ("create_material", ("POST",), WRITE_MATERIALS),
        ("revise_material", ("PATCH",), WRITE_MATERIALS),
        ("delete_material", ("DELETE",), WRITE_MATERIALS),
    )
    for method in methods
}


def bad_input(message="请检查资料参数"):
    return AccessDenied(400, 1000, message)


def material_id(value):
    if not MATERIAL_ID.fullmatch(value):
        raise bad_input("资料标识格式无效")
    return value


def _query(allowed=()):
    if request.args.keys() - set(allowed) or any(
        len(values) != 1 for _, values in request.args.lists()
    ):
        raise bad_input()


def _positive(name, default, ceiling):
    value = request.args.get(name, str(default))
    if not re.fullmatch(r"[0-9]+", value):
        raise bad_input()
    digits = value.lstrip("0")
    if not digits:
        raise bad_input()
    if len(digits) > len(str(ceiling)):
        return ceiling
    return min(int(digits), ceiling)


def _title(value):
    if not isinstance(value, str):
        raise bad_input()
    value = value.strip()
    if not 1 <= len(value) <= 120 or "\0" in value:
        raise bad_input("资料标题须为 1 至 120 字符")
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise bad_input() from None
    return value


def _json(limit):
    request.max_content_length = limit
    if request.mimetype != "application/json":
        raise bad_input()
    result = request.get_json()
    if not isinstance(result, dict):
        raise bad_input()
    return result


def _file():
    request.max_content_length = 2 * MATERIAL_LIMIT
    request.max_form_memory_size = 128 * 1024
    request.max_form_parts = 2
    if (
        set(request.form) != {"title"}
        or len(request.form.getlist("title")) != 1
        or set(request.files) != {"file"}
        or len(request.files.getlist("file")) != 1
    ):
        raise bad_input("请提供标题和一个 UTF-8 TXT 或 Markdown 文件")
    file = request.files["file"]
    name = file.filename or ""
    if (
        not name
        or len(name.encode("utf-8")) > 255
        or name in {".", ".."}
        or any(c in "/\\:" or ord(c) < 32 or 127 <= ord(c) <= 159 for c in name)
    ):
        raise bad_input("文件名无效")
    source = FORMATS.get("." + name.rsplit(".", 1)[-1].lower()) if "." in name else None
    types = {"application/octet-stream", "text/plain"}
    if source == "md":
        types.add("text/markdown")
    if source is None or file.mimetype not in types:
        raise bad_input("仅支持 UTF-8 TXT 或 Markdown 文件")
    return request.form["title"], source, file.stream.read(MATERIAL_LIMIT + 1)


def _upload():
    if request.mimetype == "multipart/form-data":
        title, source, content = _file()
    else:
        payload = _json(8 * MATERIAL_LIMIT)
        if payload.keys() != {"title", "text"} or not isinstance(payload["text"], str):
            raise bad_input()
        title, source, content = (
            payload["title"],
            "text",
            payload["text"].encode("utf-8"),
        )
    if len(content) > MATERIAL_LIMIT:
        raise bad_input("原文大小须在 1 MiB 以内")
    decoded = content.decode("utf-8-sig")
    if not decoded.strip() or "\0" in decoded:
        raise bad_input("原文不能为空白或包含空字符")
    media = "text/markdown" if source == "md" else "text/plain"
    return _title(title), source, media, content, len(decoded)


def install_materials(app, service):
    @app.after_request
    def material_response(response):
        if request.path == "/api/v1/materials" or request.path.startswith(
            "/api/v1/materials/"
        ):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/v1/materials")
    def list_materials():
        _query(("page", "page_size"))
        return success(
            service.list(
                g.identity,
                _positive("page", 1, 2**31 - 1),
                _positive("page_size", 20, 100),
            )
        )

    @app.get("/api/v1/materials/<value>")
    def read_material(value):
        _query()
        metadata, content = service.read(g.identity, material_id(value))
        return success({**metadata, "text": content.decode("utf-8-sig")})

    @app.get("/api/v1/materials/<value>/download")
    def download_material(value):
        _query()
        metadata, content = service.read(g.identity, material_id(value))
        extension = "md" if metadata["source_format"] == "md" else "txt"
        response = send_file(
            BytesIO(content),
            mimetype="application/octet-stream",
            as_attachment=True,
            download_name=f"{metadata['id']}.{extension}",
            conditional=False,
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.post("/api/v1/materials")
    def create_material():
        _query()
        key = request.headers.get("Idempotency-Key", "")
        if not REQUEST_KEY.fullmatch(key):
            raise bad_input("上传标识格式无效")
        try:
            payload = _upload()
        except (BadRequest, RequestEntityTooLarge, UnicodeError):
            raise bad_input("请检查原文格式和大小") from None
        return success(
            service.create(
                g.identity, request.cookies.get(COOKIE), key.encode("ascii"), *payload
            )
        ), 201

    @app.patch("/api/v1/materials/<value>")
    def revise_material(value):
        _query()
        target = material_id(value)
        try:
            fields = _json(4096)
        except (BadRequest, RequestEntityTooLarge):
            raise bad_input() from None
        if (
            fields.keys() - {"revision", "title", "sort_order"}
            or len(fields) < 2
            or type(fields.get("revision")) is not int
            or not 1 <= fields["revision"] <= 2**31 - 1
        ):
            raise bad_input()
        revision = fields.pop("revision")
        if "title" in fields:
            fields["title"] = _title(fields["title"])
        if "sort_order" in fields and (
            type(fields["sort_order"]) is not int
            or not 0 <= fields["sort_order"] <= 1_000_000
        ):
            raise bad_input()
        return success(
            service.revise(
                g.identity, request.cookies.get(COOKIE), target, revision, fields
            )
        )

    @app.delete("/api/v1/materials/<value>")
    def delete_material(value):
        _query()
        if request.content_length or request.headers.get("Transfer-Encoding"):
            raise bad_input()
        target = material_id(value)
        service.remove(g.identity, request.cookies.get(COOKIE), target)
        return success({"id": target, "deleted": True})
