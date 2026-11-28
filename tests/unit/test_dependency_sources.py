"""隔离集成可改变镜像来源，但不允许解除内容摘要锁定。"""

import subprocess

import pytest

from scripts.dependency_sources import mirrored_image, resolve_test_mirror
from tests.integration.test_compose import (
    mirrored_dependencies,
    pull_dependencies,
    start_stack,
)


def configuration():
    return {
        "services": {
            "mysql": {
                "image": "public.ecr.aws/docker/library/mysql:8.4@sha256:" + "a" * 64
            },
            "qdrant": {"image": "qdrant/qdrant:v1.15.3@sha256:" + "b" * 64},
            "kafka": {"image": "apache/kafka:4.1.2@sha256:" + "c" * 64},
            "kafka-topics": {"image": "apache/kafka:4.1.2@sha256:" + "c" * 64},
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


def test_mirror_preserves_gateway_digest_for_direct_runtime():
    original = "nginx:1.30-alpine@sha256:" + "c" * 64
    assert mirrored_image("gateway", original, "mirror.example") == (
        "mirror.example/library/nginx:1.30-alpine@sha256:" + "c" * 64
    )


def test_mirror_preserves_browser_base_digest():
    original = "public.ecr.aws/docker/library/node:22-alpine@sha256:" + "d" * 64
    assert mirrored_image("browser", original, "mirror.example") == (
        "mirror.example/library/node:22-alpine@sha256:" + "d" * 64
    )


def test_ci_uses_locked_test_mirror_without_changing_local_default():
    assert resolve_test_mirror({"CI": "true"}) == "docker.m.daocloud.io"
    assert resolve_test_mirror({}) is None
    assert (
        resolve_test_mirror(
            {"CI": "true", "CAMPUSCLAW_TEST_DOCKER_MIRROR": "mirror.example"}
        )
        == "mirror.example"
    )


def test_dependency_pull_retries_transient_registry_failure(monkeypatch):
    calls = []

    def compose(*args, **kwargs):
        calls.append((args, kwargs))
        if len(calls) < 3:
            raise subprocess.CalledProcessError(1, args)

    monkeypatch.setattr("tests.integration.test_compose.time.sleep", lambda _: None)
    pull_dependencies(compose, "mysql", "qdrant")

    assert calls == [
        (("pull", "--quiet", "mysql", "qdrant"), {"timeout": 120}),
        (("pull", "--quiet", "mysql", "qdrant"), {"timeout": 120}),
        (("pull", "--quiet", "mysql", "qdrant"), {"timeout": 120}),
    ]


def test_dependency_pull_keeps_final_failure(monkeypatch):
    def compose(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args)

    monkeypatch.setattr("tests.integration.test_compose.time.sleep", lambda _: None)
    with pytest.raises(subprocess.CalledProcessError):
        pull_dependencies(compose, "mysql", "qdrant")


def test_stack_start_retries_transient_build_service_failure(monkeypatch):
    calls = []

    def compose(*args):
        calls.append(args)
        if len(calls) == 1:
            raise subprocess.CalledProcessError(1, args)

    monkeypatch.setattr("tests.integration.test_compose.time.sleep", lambda _: None)
    start_stack(compose)

    assert calls == [("up", "--build", "-d"), ("up", "--build", "-d")]


def test_mirror_preserves_teaching_kafka_digest():
    override = mirrored_dependencies(
        configuration(), "mirror.example", ("kafka", "kafka-topics")
    )
    image = "mirror.example/apache/kafka:4.1.2@sha256:" + "c" * 64
    assert override == {
        "services": {
            "kafka": {"image": image},
            "kafka-topics": {"image": image},
        }
    }


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
