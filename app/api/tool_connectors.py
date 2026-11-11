"""本班教师的工具连接管理接口。"""

from flask import g, request

from app.api.ai_apps import body, pagination
from app.api.auth import COOKIE
from app.api.http import success
from app.api.materials import _query
from app.services.ai_contracts import AI_CONFIGURE, identifier

ROUTES = (
    ("tool_connector_options", ("GET", "HEAD")),
    ("list_tool_connectors", ("GET", "HEAD")),
    ("register_tool_connector", ("POST",)),
    ("read_tool_connector", ("GET", "HEAD")),
    ("delete_tool_connector", ("DELETE",)),
    ("connect_tool_connector", ("POST",)),
    ("disconnect_tool_connector", ("DELETE",)),
    ("list_connector_tools", ("GET", "HEAD")),
    ("review_connector_tool", ("PATCH",)),
    ("tool_call_audit", ("GET", "HEAD")),
)
TOOL_POLICIES = {
    (endpoint, method): AI_CONFIGURE
    for endpoint, methods in ROUTES
    for method in methods
}


def install_tool_connectors(app, service):
    base = "/api/v1/tool-connectors"
    resource = base + "/<resource_id>"

    def actor():
        return g.identity, request.cookies.get(COOKIE)

    @app.after_request
    def tool_no_cache(response):
        if request.endpoint in {endpoint for endpoint, _ in ROUTES}:
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/v1/tool-connector-options")
    def tool_connector_options():
        _query()
        return success({"items": service.options(*actor())})

    @app.get("/api/v1/tool-call-audit")
    def tool_call_audit():
        return success(service.audit(*actor(), *pagination()))

    @app.get(base)
    def list_tool_connectors():
        return success(service.list(*actor(), *pagination()))

    @app.post(base)
    def register_tool_connector():
        _query()
        return success(service.register(*actor(), body({"alias", "key"}))), 201

    @app.get(resource)
    def read_tool_connector(resource_id):
        _query()
        return success(service.read(*actor(), identifier(resource_id)))

    @app.delete(resource)
    def delete_tool_connector(resource_id):
        _query()
        return success(
            service.disconnect(*actor(), identifier(resource_id), remove=True)
        )

    @app.post(resource + "/connections")
    def connect_tool_connector(resource_id):
        _query()
        body(set())
        return success(service.connect(*actor(), identifier(resource_id)))

    @app.delete(resource + "/connections/current")
    def disconnect_tool_connector(resource_id):
        _query()
        return success(service.disconnect(*actor(), identifier(resource_id)))

    @app.get(resource + "/tools")
    def list_connector_tools(resource_id):
        _query()
        return success({"items": service.tools(*actor(), identifier(resource_id))})

    @app.patch(resource + "/tools/<name>")
    def review_connector_tool(resource_id, name):
        _query()
        return success(service.review(*actor(), identifier(resource_id), name, body()))
