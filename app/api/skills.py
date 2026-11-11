"""教师班级技能API：与应用入口共用认证、请求头和错误封装。"""

from flask import g, request

from app.api.ai_apps import body, pagination
from app.api.auth import COOKIE
from app.api.http import success
from app.api.materials import _query
from app.services.ai_contracts import AI_CONFIGURE, bad, identifier
from app.services.skills import SkillService

SKILL_POLICIES = {
    (endpoint, method): AI_CONFIGURE
    for endpoint, methods in (
        ("list_skills", ("GET", "HEAD")),
        ("read_skill", ("GET", "HEAD")),
        ("create_skill", ("POST",)),
        ("update_skill", ("PATCH",)),
        ("delete_skill", ("DELETE",)),
    )
    for method in methods
}


def install_skills(app, ai_apps, tool_connectors=None):
    service = SkillService(ai_apps, tool_connectors)

    @app.after_request
    def skills_no_cache(response):
        if request.endpoint in {endpoint for endpoint, _ in SKILL_POLICIES}:
            response.headers["Cache-Control"] = "no-store"
        return response

    def payload():
        # 在JSON解码之前拒绝超限，重复键由共用解析器拒绝。
        if request.content_length is not None and request.content_length > 8192:
            raise bad("技能清单不得超过 8 KiB")
        value = body()
        if len(request.get_data()) > 8192:
            raise bad("技能清单不得超过 8 KiB")
        return value

    @app.get("/api/v1/skills")
    def list_skills():
        return success(
            service.list(g.identity, request.cookies.get(COOKIE), *pagination())
        )

    @app.get("/api/v1/skills/<resource_id>")
    def read_skill(resource_id):
        _query()
        return success(
            service.read(
                g.identity, request.cookies.get(COOKIE), identifier(resource_id)
            )
        )

    @app.post("/api/v1/skills")
    def create_skill():
        return success(
            service.save(g.identity, request.cookies.get(COOKIE), payload())
        ), 201

    @app.patch("/api/v1/skills/<resource_id>")
    def update_skill(resource_id):
        return success(
            service.save(
                g.identity,
                request.cookies.get(COOKIE),
                payload(),
                identifier(resource_id),
            )
        )

    @app.delete("/api/v1/skills/<resource_id>")
    def delete_skill(resource_id):
        data = body({"revision"})
        return success(
            service.delete(
                g.identity,
                request.cookies.get(COOKIE),
                identifier(resource_id),
                data["revision"],
            )
        )
