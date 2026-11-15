"""配置写入夹具使用与浏览器相同的令牌签发接口。"""

from werkzeug.exceptions import HTTPException

from app.api.csrf import CSRF_HEADER
from app.api.operation_audit import CONFIGURATION_ENDPOINTS


def configuration_headers(client, method, path, origin, headers):
    if method not in {"POST", "PATCH", "DELETE"}:
        return headers
    route = client.application.url_map.bind("campusclaw.test")
    try:
        action, _ = route.match(path.split("?", 1)[0], method=method)
    except HTTPException:
        return headers
    if action not in CONFIGURATION_ENDPOINTS:
        return headers
    issued = client.post(
        "/api/v1/auth/csrf-tokens",
        base_url=origin,
        headers=headers,
        json={"action": action},
    )
    assert issued.status_code == 200, (action, issued.status_code)
    assert issued.headers["Cache-Control"] == "no-store"
    return headers | {CSRF_HEADER: issued.json["data"]["token"]}
