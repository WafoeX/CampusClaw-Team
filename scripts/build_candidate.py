"""构建并启动同一 Git 修订的应用与 MCP 镜像，输出脱敏追溯记录。"""

import argparse
import json
import os
import re
import secrets
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

from scripts.dependency_sources import mirrored_dependencies
from scripts.verify_runtime import ROOT, VerificationError, inspect_probes

PROJECT_CODE = ("srv/campusclaw/app/", "srv/campusclaw/mcp-server/")
BUILD_TOOL = re.compile(
    r"usr/(?:local/)?bin/(?:uvx?|pip(?:3(?:\.\d+)?)?|gcc|g\+\+|cc|make)"
)
PACKAGING_MODULES = (
    "usr/local/lib/python3.13/ensurepip/",
    "usr/local/lib/python3.13/site-packages/pip/",
    "srv/campusclaw/.venv/lib/python3.13/site-packages/pip/",
)


def run(*args, env, timeout=60, stderr=None):
    return subprocess.check_output(
        args, cwd=ROOT, env=env, text=True, timeout=timeout, stderr=stderr
    ).strip()


def inspect_runtime_layers(archive_path, entrypoint):
    found = False
    with tarfile.open(archive_path) as archive:
        manifest = json.load(archive.extractfile("manifest.json"))
        (image,) = manifest
        for layer in image["Layers"]:
            with tarfile.open(fileobj=archive.extractfile(layer), mode="r|*") as files:
                for member in files:
                    path = member.name.removeprefix("./").lstrip("/")
                    if (
                        (path.startswith(PROJECT_CODE) and path.endswith(".py"))
                        or BUILD_TOOL.fullmatch(path)
                        or path.startswith(PACKAGING_MODULES)
                    ):
                        raise VerificationError(f"镜像层含有不应交付的文件：{path}")
                    found |= path == entrypoint and member.isfile()
    if not found:
        raise VerificationError(f"镜像缺少可运行的字节码入口：{entrypoint}")
    return len(image["Layers"])


def build_image(target, repository, revision, metadata_path, env):
    tag = f"{repository}:{revision}"
    run(
        "docker",
        "buildx",
        "build",
        "--load",
        "--target",
        target,
        "--tag",
        tag,
        "--build-arg",
        f"APP_BUILD_REVISION={revision}",
        "--metadata-file",
        str(metadata_path),
        ".",
        env=env,
        timeout=420,
    )
    metadata = json.loads(metadata_path.read_text())
    image = json.loads(run("docker", "image", "inspect", tag, env=env))[0]
    digest = metadata["containerimage.digest"]
    if (
        not re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
        or image["Id"] not in (digest, metadata.get("containerimage.config.digest"))
        or image["Config"]["Labels"]["org.opencontainers.image.revision"] != revision
        or tag not in image["RepoTags"]
    ):
        raise VerificationError("构建摘要、镜像标签和源码修订不一致")
    archive = metadata_path.with_suffix(".tar")
    run("docker", "image", "save", "--output", str(archive), tag, env=env, timeout=180)
    entrypoint = (
        "srv/campusclaw/app/__main__.pyc"
        if target == "app"
        else "srv/campusclaw/mcp-server/teaching_server.pyc"
    )
    layers = inspect_runtime_layers(archive, entrypoint)
    return {"tag": tag, "digest": digest, "id": image["Id"], "layers_checked": layers}


def pull_dependency(compose, service):
    for retry_delay in (10, 30, 0):
        try:
            compose(
                "pull",
                "--policy",
                "missing",
                service,
                stderr=subprocess.PIPE,
                timeout=180,
            )
            return
        except subprocess.CalledProcessError as error:
            if not retry_delay or "toomanyrequests" not in error.stderr.lower():
                print(error.stderr, file=sys.stderr, end="")
                raise
            print(f"{service} 镜像仓库限流，{retry_delay} 秒后重试", file=sys.stderr)
            time.sleep(retry_delay)


def start_images(revision, images, env, folder, mirror_host=None):
    project = "campusclaw-candidate-" + secrets.token_hex(8)
    env = {
        **env,
        "APP_BUILD_REVISION": revision,
        "APP_HOST_PORT": "0",
        "MYSQL_DATABASE": "campusclaw_" + secrets.token_hex(8),
        "MYSQL_USER": "campusclaw_test",
        "MYSQL_PASSWORD": secrets.token_hex(16),
        "MYSQL_ROOT_PASSWORD": secrets.token_hex(16),
        "QDRANT_API_KEY": secrets.token_hex(16),
        "MCP_SERVICE_TOKEN": secrets.token_hex(16),
    }

    compose_files = ["--file", "docker-compose.yml"]
    if mirror_host:
        configuration = json.loads(
            run(
                "docker",
                "compose",
                "--file",
                "docker-compose.yml",
                "--env-file",
                os.devnull,
                "--profile",
                "tools",
                "config",
                "--format",
                "json",
                env=env,
            )
        )
        override = folder / "dependency-sources.json"
        override.write_text(
            json.dumps(mirrored_dependencies(configuration, mirror_host))
        )
        compose_files.extend(("--file", str(override)))

    def compose(*args, timeout=60, stderr=None):
        return run(
            "docker",
            "compose",
            "--project-name",
            project,
            *compose_files,
            "--env-file",
            os.devnull,
            "--profile",
            "tools",
            *args,
            env=env,
            timeout=timeout,
            stderr=stderr,
        )

    try:
        for service in ("mysql", "qdrant"):
            pull_dependency(compose, service)
        compose(
            "up",
            "--no-build",
            "--pull",
            "never",
            "--wait",
            "--wait-timeout",
            "120",
            timeout=150,
        )
        for service, image in images.items():
            container = compose("ps", "--quiet", service)
            running_image = run(
                "docker", "inspect", "--format", "{{.Image}}", container, env=env
            )
            if running_image != image["id"]:
                raise VerificationError(f"{service} 容器未使用刚构建的镜像")
        port = int(compose("port", "app", "8080").rsplit(":", 1)[1])
        deadline = time.monotonic() + 25
        while True:
            try:
                probes = inspect_probes(port, revision)
                return {path: row["http_status"] for path, row in probes.items()}
            except (OSError, VerificationError):
                if time.monotonic() >= deadline:
                    raise
                time.sleep(1)
    finally:
        compose("down", "--volumes", "--remove-orphans")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("revision", help="检出的完整 Git 提交号")
    parser.add_argument("--mirror-host", help="显式依赖来源主机，保持全部摘要")
    args = parser.parse_args()
    revision = args.revision
    env = {key: os.environ[key] for key in ("PATH", "HOME") if key in os.environ}
    if not re.fullmatch(r"[0-9a-f]{40}", revision) or revision != run(
        "git", "rev-parse", "HEAD", env=env
    ):
        parser.error("构建修订必须与 HEAD 一致")
    if run(
        "git",
        "status",
        "--porcelain",
        "--",
        "app",
        "mcp-server",
        "Dockerfile",
        "docker-compose.yml",
        ".dockerignore",
        "pyproject.toml",
        "uv.lock",
        env=env,
    ):
        parser.error("候选镜像的构建输入存在未提交改动")
    if not run(
        "docker",
        "context",
        "inspect",
        "--format",
        "{{.Endpoints.docker.Host}}",
        env=env,
    ).startswith("unix://"):
        parser.error("候选构建和启动需要本机 Docker")
    with tempfile.TemporaryDirectory(prefix="campusclaw-build-") as temporary:
        folder = Path(temporary)
        images = {
            service: build_image(
                target, repository, revision, folder / f"{target}.json", env
            )
            for service, target, repository in (
                ("app", "app", "campusclaw-skeleton"),
                ("mcp-server", "mcp-service", "campusclaw-mcp"),
            )
        }
        probes = start_images(revision, images, env, folder, args.mirror_host)
    print(
        json.dumps(
            {
                "source_revision": revision,
                "ci_run_id": os.environ.get("GITHUB_RUN_ID"),
                "images": images,
                "running_revision": revision,
                "http_status": probes,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
