"""主机侧隔离环境的依赖镜像来源；保持已知内容摘要与应用目标。"""

import re

SOURCES = {
    "mysql": ("public.ecr.aws/docker/library/mysql:", "library/mysql:"),
    "qdrant": ("qdrant/qdrant:", "qdrant/qdrant:"),
    "gateway": ("nginx:", "library/nginx:"),
    "browser": ("public.ecr.aws/docker/library/node:", "library/node:"),
    "kafka": ("apache/kafka:", "apache/kafka:"),
    "kafka-topics": ("apache/kafka:", "apache/kafka:"),
}
CI_MIRROR = "docker.m.daocloud.io"


def resolve_test_mirror(environment):
    explicit = environment.get("CAMPUSCLAW_TEST_DOCKER_MIRROR")
    if explicit:
        return explicit
    return CI_MIRROR if environment.get("CI") == "true" else None


def mirrored_dependencies(configuration, mirror, services=("mysql", "qdrant")):
    return {
        "services": {
            service: {
                "image": mirrored_image(
                    service, configuration["services"][service]["image"], mirror
                )
            }
            for service in services
        }
    }


def mirrored_image(service, original, mirror):
    if not re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)+(?::[0-9]{1,5})?", mirror):
        raise ValueError("测试镜像来源必须是无路径和凭据的仓库主机名")
    prefix, path = SOURCES[service]
    if not original.startswith(prefix) or not re.search(
        r"@sha256:[0-9a-f]{64}$", original
    ):
        raise ValueError("测试镜像必须保留已锁定来源与完整摘要")
    return f"{mirror}/{path}{original.removeprefix(prefix)}"
