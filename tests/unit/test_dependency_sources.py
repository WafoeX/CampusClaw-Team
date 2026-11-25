"""隔离集成可改变镜像来源，但不允许解除内容摘要锁定。"""

import pytest

from tests.integration.test_compose import mirrored_dependencies


def configuration():
    return {
        "services": {
            "mysql": {
                "image": "public.ecr.aws/docker/library/mysql:8.4@sha256:" + "a" * 64
            },
            "qdrant": {"image": "qdrant/qdrant:v1.15.3@sha256:" + "b" * 64},
            "app": {"image": "local-app:fixture"},
        }
    }


def test_mirror_preserves_both_digests_and_does_not_override_application():
    original = configuration()
    override = mirrored_dependencies(original, "mirror.example")
    assert override == {
        "services": {
            "mysql": {"image": "mirror.example/library/mysql:8.4@sha256:" + "a" * 64},
            "qdrant": {
                "image": "mirror.example/qdrant/qdrant:v1.15.3@sha256:" + "b" * 64
            },
        }
    }
    assert original == configuration()


@pytest.mark.parametrize(
    "mirror",
    [
        "https://mirror.example",
        "a:b@mirror.example",
        "mirror.example/path",
        "mirror.example?x=1",
        "mirror.example\n",
    ],
)
def test_mirror_rejects_credentials_paths_and_invalid_host(mirror):
    with pytest.raises(ValueError):
        mirrored_dependencies(configuration(), mirror)


@pytest.mark.parametrize(
    "image",
    [
        "qdrant/qdrant:latest",
        "other/qdrant:v1@sha256:" + "a" * 64,
        "qdrant/qdrant:v1@sha256:abc",
    ],
)
def test_mirror_cannot_substitute_unpinned_or_unexpected_image(image):
    original = configuration()
    original["services"]["qdrant"]["image"] = image
    with pytest.raises(ValueError):
        mirrored_dependencies(original, "mirror.example")
