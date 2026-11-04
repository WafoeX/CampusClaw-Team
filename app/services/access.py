from dataclasses import dataclass


@dataclass(frozen=True)
class Identity:
    subject_id: str
    class_id: str
    permissions: frozenset[str]


@dataclass(frozen=True)
class ResourceScope:
    class_id: str
    private_owner_id: str | None = None


class AccessDenied(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def authorize(resolve_identity, permission):
    try:
        identity = resolve_identity()
    except Exception:
        raise AccessDenied(503, 1500, "依赖服务暂不可用，请稍后重试") from None
    if identity is None:
        raise AccessDenied(401, 1100, "登录状态无效，请重新登录")
    if permission not in identity.permissions:
        raise AccessDenied(403, 1200, "当前账号无此操作权限")
    return identity


def require_resource(identity, scope):
    if (
        scope is None
        or scope.class_id != identity.class_id
        or (
            scope.private_owner_id is not None
            and scope.private_owner_id != identity.subject_id
        )
    ):
        raise AccessDenied(404, 1300, "资源不存在或不可访问")
