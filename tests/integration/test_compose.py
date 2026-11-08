import json
import os
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import pytest

from scripts.verify_runtime import inspect_probes
from tests.integration.streaming_proxy_check import verify_streaming_proxy

ROOT = Path(__file__).resolve().parents[2]
COMPOSE_OVERRIDES = {
    "COMPOSE_FILE",
    "COMPOSE_ENV_FILES",
    "COMPOSE_PROJECT_NAME",
    "DOCKER_HOST",
    "DOCKER_CONTEXT",
    "CAMPUSCLAW_TEST_MYSQL_URL",
    "CAMPUSCLAW_TEST_VOLUME",
}


def scan_image(scanner, image, folder, env):
    archive = folder / "candidate.tar"
    cache = Path(os.environ["CAMPUSCLAW_SCANNER_CACHE"])
    try:
        subprocess.run(
            ["docker", "save", "--output", str(archive), image],
            env=env,
            check=True,
            timeout=180,
        )
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--mount",
                f"type=bind,src={folder},dst=/scan,readonly",
                "--mount",
                f"type=bind,src={cache},dst=/cache",
                scanner,
                "image",
                "--input",
                "/scan/candidate.tar",
                "--cache-dir",
                "/cache",
                "--db-repository",
                "ghcr.io/aquasecurity/trivy-db:2",
                "--no-progress",
                "--scanners",
                "vuln",
                "--severity",
                "HIGH,CRITICAL",
                "--exit-code",
                "1",
            ],
            env=env,
            check=True,
            timeout=420,
        )
    finally:
        archive.unlink(missing_ok=True)


def eventually(action, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            result = action()
        except (OSError, urllib.error.URLError, subprocess.CalledProcessError):
            result = None
        if result:
            return result
        time.sleep(0.25)
    pytest.fail("隔离服务在时限内未达到预期状态")


def assert_project_clean(project, env):
    label = f"label=com.docker.compose.project={project}"
    for list_command in (
        ["ps", "-aq"],
        ["network", "ls", "-q"],
        ["volume", "ls", "-q"],
    ):
        remaining = subprocess.check_output(
            ["docker", *list_command, "--filter", label],
            env=env,
            text=True,
            timeout=30,
        ).strip()
        assert not remaining, f"隔离项目 {project} 清理后仍有资源：{remaining}"


@pytest.fixture(scope="module")
def stack(tmp_path_factory):
    overrides = sorted(key for key in COMPOSE_OVERRIDES if os.environ.get(key))
    if overrides:
        pytest.fail(f"隔离集成禁止外部目标覆盖：{', '.join(overrides)}")
    folder = tmp_path_factory.mktemp("skeleton-compose")
    run_id = uuid.uuid4().hex
    project = f"campusclaw-check-{run_id}"
    version = "00000000" + run_id
    config = folder / "compose.env"
    config.write_text(
        "\n".join(
            (
                f"MYSQL_DATABASE=campusclaw_test_{run_id}",
                "MYSQL_USER=campusclaw_test",
                f"MYSQL_PASSWORD={uuid.uuid4().hex}",
                f"MYSQL_ROOT_PASSWORD={uuid.uuid4().hex}",
                f"QDRANT_API_KEY={uuid.uuid4().hex}",
                "APP_HOST_PORT=0",
                f"APP_BUILD_REVISION={version}",
            )
        )
    )
    env = {key: os.environ[key] for key in ("PATH", "HOME") if key in os.environ}
    endpoint = subprocess.check_output(
        ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
        env=env,
        text=True,
        timeout=15,
    ).strip()
    if not endpoint.startswith("unix://"):
        pytest.fail("隔离集成需要本机 Docker Unix socket")
    command = [
        "docker",
        "compose",
        "--project-name",
        project,
        "--env-file",
        str(config),
        "--file",
        str(ROOT / "docker-compose.yml"),
    ]

    def compose(*args, check=True):
        return subprocess.run(
            [*command, *args],
            cwd=ROOT,
            env=env,
            check=check,
            stdout=subprocess.PIPE,
            text=True,
            timeout=420,
        ).stdout.strip()

    try:
        compose("up", "--build", "-d")
        scanner = os.environ.get("CAMPUSCLAW_IMAGE_SCANNER")
        if scanner:
            scan_image(scanner, f"campusclaw-skeleton:{version}", folder, env)
        port = compose("port", "app", "8080").rsplit(":", 1)[1]

        def request(path):
            try:
                response = urllib.request.urlopen(
                    f"http://127.0.0.1:{port}{path}", timeout=3
                )
            except urllib.error.HTTPError as error:
                response = error
            with response:
                return response.status, json.load(response), response.headers

        def status(expected):
            def observe():
                code, body, headers = request("/health")
                return (code, body, headers) if body["status"] == expected else None

            return eventually(observe)

        status("ready")
        yield compose, request, status, version
    finally:
        try:
            compose("down", "--volumes", "--remove-orphans")
            assert_project_clean(project, env)
        finally:
            image = f"campusclaw-skeleton:{version}"
            present = (
                subprocess.run(
                    ["docker", "image", "inspect", image],
                    env=env,
                    capture_output=True,
                    timeout=30,
                    check=False,
                ).returncode
                == 0
            )
            if present:
                subprocess.run(
                    ["docker", "image", "rm", image], env=env, timeout=60, check=True
                )


def test_RT_N01_RT_F03_RT_B01_RT_B04_cold_start_and_recovery(stack, tmp_path):
    compose, request, status, version = stack
    code, ready, headers = status("ready")
    assert code == 200 and ready["version"] == version
    assert ready["request_id"] == headers["X-Request-ID"]
    assert ready["dependencies"] == {"mysql": "ready", "qdrant": "ready"}
    published = {
        row["Service"]: [
            publisher
            for publisher in row["Publishers"] or []
            if publisher.get("PublishedPort")
        ]
        for row in map(json.loads, compose("ps", "--format", "json").splitlines())
    }
    assert set(published) == {"app", "mysql", "qdrant"}
    assert published["mysql"] == published["qdrant"] == []
    assert len(published["app"]) == 1
    assert published["app"][0]["URL"] == "127.0.0.1"
    assert published["app"][0]["TargetPort"] == 8080
    port = int(compose("port", "app", "8080").rsplit(":", 1)[1])
    observed = inspect_probes(port, version)
    assert set(observed) == {"/health", "/live"}
    verify_auth_migration(compose)
    verify_chapter_migration(compose)
    verify_chapter_api(compose)
    verify_index_foundation(compose)
    verify_index_builds(compose)
    verify_assistant_storage(compose)
    verify_ai_apps(compose)
    verify_rate_limits(compose)
    verify_retrieval(compose, "setup")
    verify_evaluation(compose)

    compose("stop", "mysql")
    code, unready, _ = status("not_ready")
    assert code == 503 and request("/live")[0] == 200
    assert unready["dependencies"] == {"mysql": "unavailable", "qdrant": "ready"}
    compose("start", "mysql")
    assert status("ready")[0] == 200

    compose("stop", "qdrant")
    code, degraded, _ = status("degraded")
    assert code == 200
    assert degraded["dependencies"] == {"mysql": "ready", "qdrant": "unavailable"}
    verify_retrieval(compose, "down")
    compose("start", "qdrant")
    assert status("ready")[0] == 200

    verify_retrieval(compose, "delete")
    verify_streaming_proxy(compose, tmp_path / "streaming-proxy")

    started = time.monotonic()
    compose("kill", "-s", "SIGTERM", "app")
    assert status("not_ready")[0] == 503
    eventually(lambda: compose("ps", "--status", "exited", "-q", "app"), timeout=30)
    assert time.monotonic() - started <= 30
    rows = [
        json.loads(line)
        for line in compose("logs", "--no-log-prefix", "app").splitlines()
    ]
    assert any(
        row.get("event") == "draining" and row["version"] == version for row in rows
    )
    assert any(row.get("event") == "stopped" and row["forced"] is False for row in rows)


def verify_auth_migration(compose):
    # 任务 1.2：已就绪骨架库与空库，迁移重跑、种子保留和降级。
    compose(
        "exec",
        "-T",
        "app",
        "python",
        "-c",
        Path(__file__).with_name("auth_runtime.py").read_text(),
    )


def verify_rate_limits(compose):
    compose(
        "exec",
        "-T",
        "app",
        "python",
        "-c",
        Path(__file__).with_name("rate_limit_runtime.py").read_text(),
    )


def verify_chapter_migration(compose):
    compose(
        "exec",
        "-T",
        "app",
        "python",
        "-c",
        Path(__file__).with_name("chapter_migration_runtime.py").read_text(),
    )


def verify_chapter_api(compose):
    compose(
        "exec",
        "-T",
        "app",
        "python",
        "-c",
        Path(__file__).with_name("chapter_api_runtime.py").read_text(),
    )


def verify_index_foundation(compose):
    compose(
        "exec",
        "-T",
        "app",
        "python",
        "-c",
        Path(__file__).with_name("index_foundation_runtime.py").read_text(),
    )


def verify_index_builds(compose):
    compose(
        "exec",
        "-T",
        "app",
        "python",
        "-c",
        Path(__file__).with_name("index_build_runtime.py").read_text(),
    )


def verify_retrieval(compose, phase):
    compose(
        "exec",
        "-T",
        "app",
        "python",
        "-c",
        Path(__file__).with_name("retrieval_runtime.py").read_text(),
        phase,
    )


def verify_evaluation(compose):
    fixture = ROOT / "tests/eval/retrieval-evaluation.json"
    compose(
        "exec",
        "-T",
        "app",
        "python",
        "-c",
        "from pathlib import Path; import sys; Path('/tmp/campusclaw-retrieval-evaluation.json').write_text(sys.argv[1])",
        fixture.read_text(),
    )
    output = compose(
        "exec",
        "-T",
        "app",
        "python",
        "-c",
        Path(__file__).with_name("evaluation_runtime.py").read_text(),
    )
    reports = [
        json.loads(line.removeprefix("EVAL_RESULT:"))
        for line in output.splitlines()
        if line.startswith("EVAL_RESULT:")
    ]
    assert len(reports) == 1 and reports[0]["questions"] >= 30
    folder = ROOT / "reports/2026-11-06-index-builds"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "evaluation.json").write_text(
        json.dumps(reports[0], ensure_ascii=False, indent=2) + "\n"
    )


def verify_assistant_storage(compose):
    compose(
        "exec",
        "-T",
        "app",
        "python",
        "-c",
        Path(__file__).with_name("assistant_storage_runtime.py").read_text(),
    )


def verify_ai_apps(compose):
    compose(
        "exec",
        "-T",
        "app",
        "python",
        "-c",
        "from pathlib import Path; import sys; Path('/tmp/feedback_runtime.py').write_text(sys.argv[1])",
        Path(__file__).with_name("feedback_runtime.py").read_text(),
    )
    compose(
        "exec",
        "-T",
        "app",
        "python",
        "-c",
        Path(__file__).with_name("ai_apps_runtime.py").read_text(),
    )
