import json
import os
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import pytest

from app.config import ChatSettings, ConfigError
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


@pytest.fixture
def stack(tmp_path_factory):
    overrides = sorted(key for key in COMPOSE_OVERRIDES if os.environ.get(key))
    if overrides:
        pytest.fail(f"隔离集成禁止外部目标覆盖：{', '.join(overrides)}")
    folder = tmp_path_factory.mktemp("skeleton-compose")
    run_id = uuid.uuid4().hex
    project = f"campusclaw-check-{run_id}"
    image_tag = "00000000" + run_id
    version = image_tag
    overlay = []
    if os.environ.get("CAMPUSCLAW_SECURITY_ASSETS"):
        version = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, timeout=15
        ).strip()
        override = folder / "security-compose.json"
        override.write_text(
            json.dumps(
                {
                    "services": {
                        "app": {"image": f"campusclaw-skeleton:{image_tag}"},
                        "mcp-server": {"image": f"campusclaw-mcp:{image_tag}"},
                    }
                }
            )
        )
        overlay = ["--file", str(override)]
    config = folder / "compose.env"
    config.touch(mode=0o600)
    real_gateway = {}
    if os.environ.get("CAMPUSCLAW_REAL_CANDIDATES") == "1":
        keys = ("CHAT_BASE_URL", "CHAT_MODEL", "CHAT_API_KEY")
        try:
            if all(key in os.environ for key in keys):
                real_gateway = {key: os.environ[key] for key in keys}
            else:
                real_gateway = {
                    key: value
                    for key, equals, value in (
                        line.partition("=")
                        for line in (ROOT / ".env").read_text().splitlines()
                    )
                    if equals and key in keys
                }
            chat = ChatSettings.load(real_gateway)
            if chat is None or not chat.api_key:
                raise ConfigError("CHAT_API_KEY")
        except (OSError, ConfigError):
            pytest.fail(
                "真实候选题验证需要在环境或私有 .env 中配置有效的三项 CHAT 设置",
                pytrace=False,
            )
    config.write_text(
        "\n".join(
            (
                f"MYSQL_DATABASE=campusclaw_test_{run_id}",
                "MYSQL_USER=campusclaw_test",
                f"MYSQL_PASSWORD={uuid.uuid4().hex}",
                f"MYSQL_ROOT_PASSWORD={uuid.uuid4().hex}",
                f"QDRANT_API_KEY={uuid.uuid4().hex}",
                f"MCP_SERVICE_TOKEN={uuid.uuid4().hex}",
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
        *overlay,
    ]

    def compose(*args, check=True, teaching=False):
        extension = (
            [
                "--file",
                str(ROOT / "docker-compose.teaching.yml"),
                "--profile",
                "teaching",
            ]
            if teaching
            else []
        )
        return subprocess.run(
            [*command, *extension, *args],
            cwd=ROOT,
            env=env | real_gateway,
            check=check,
            stdout=subprocess.PIPE,
            text=True,
            timeout=420,
        ).stdout.strip()

    try:
        compose("up", "--build", "-d")
        scanner = os.environ.get("CAMPUSCLAW_IMAGE_SCANNER")
        if scanner:
            scan_image(scanner, f"campusclaw-skeleton:{image_tag}", folder, env)
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
            compose(
                "--profile",
                "tools",
                "down",
                "--volumes",
                "--remove-orphans",
                teaching=True,
            )
            assert_project_clean(project, env)
        finally:
            for repository in ("campusclaw-skeleton", "campusclaw-mcp"):
                image = f"{repository}:{image_tag}"
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
                        ["docker", "image", "rm", image],
                        env=env,
                        timeout=60,
                        check=True,
                    )


def test_MP_N01_MP_B01_isolated_compose_teaching_service(stack, tmp_path):
    compose, _, status, version = stack
    compose("start", "app")
    status("ready")
    try:
        compose("up", "--build", "--wait", "--no-deps", "mcp-server")
        scanner = os.environ.get("CAMPUSCLAW_IMAGE_SCANNER")
        if scanner:
            scan_image(scanner, f"campusclaw-mcp:{version}", tmp_path, os.environ)
        container = json.loads(compose("ps", "--format", "json", "mcp-server"))
        assert container["Health"] == "healthy"
        assert not any(
            port.get("PublishedPort") for port in container["Publishers"] or []
        )
        assert status("ready")[0] == 200
        smoke = Path(__file__).with_name("mcp_compose_check.py").read_text()
        assert (
            compose("exec", "-T", "app", "python", "-c", smoke)
            == "教学服务内网调用通过"
        )
        assert (
            compose(
                "exec",
                "-T",
                "app",
                "python",
                "-c",
                Path(__file__).with_name("mcp_post_sse_runtime.py").read_text(),
            )
            == "独立 POST SSE 夹具互操作通过"
        )
        assert (
            compose(
                "exec",
                "-T",
                "mcp-server",
                "python",
                "-c",
                "import os; assert not any(k.startswith(('MYSQL_', 'QDRANT_', 'CHAT_')) for k in os.environ)",
            )
            == ""
        )
        compose("stop", "mcp-server")
        assert status("ready")[0] == 200
    finally:
        compose("rm", "--stop", "--force", "mcp-server")


def verify_security_precheck(compose):
    compose(
        "exec",
        "-T",
        "app",
        "python",
        "-c",
        "from pathlib import Path; import sys; Path('/tmp/session_proxy_worker.py').write_text(sys.argv[1])",
        Path(__file__).with_name("session_proxy_worker.py").read_text(),
    )
    return compose(
        "exec",
        "-T",
        "-e",
        "PYTHONPATH=/srv/campusclaw:/tmp",
        "app",
        "python",
        "-c",
        Path(__file__).with_name("security_precheck_runtime.py").read_text(),
    )


def test_PSC_N01_PSC_F01_PSC_F02_PSC_F03_PSC_F04_security_precheck(stack):
    compose, request, status, version = stack
    assert status("ready")[1]["version"] == version and request("/live")[0] == 200
    output = verify_security_precheck(compose)
    evidence = json.loads(
        next(
            line.removeprefix("SECURITY_PRECHECK ")
            for line in output.splitlines()
            if line.startswith("SECURITY_PRECHECK ")
        )
    )
    logs = [json.loads(line) for line in output.splitlines() if line.startswith("{")]
    audit = evidence["skill_audit"]
    http_rows = [
        row
        for row in logs
        if row.get("module") == "http" and row.get("request_id") == audit["request_id"]
    ]
    assert len(http_rows) == 1 and http_rows[0]["status"] == 200
    model_rows = [row for row in logs if row.get("module") == "model"]
    assert len(model_rows) == 1 and model_rows[0]["total_tokens"] == 30
    audit["usage_linked_by_request"] = (
        model_rows[0]["request_id"] == audit["request_id"]
    )
    audit["model_total_tokens"] = model_rows[0]["total_tokens"]
    print(json.dumps(evidence, ensure_ascii=False))
    assets = os.environ.get("CAMPUSCLAW_SECURITY_ASSETS")
    if assets:
        candidate = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        tracked = subprocess.check_output(
            [
                "git",
                "status",
                "--porcelain",
                "--untracked-files=all",
                "--",
                "app",
                "mcp-server",
                "Dockerfile",
                "uv.lock",
                "pyproject.toml",
                "docker-compose.yml",
            ],
            cwd=ROOT,
        )
        assert not tracked, "候选的应用、镜像或依赖输入存在未提交改动"
        folder = Path(assets).resolve()
        assert folder.is_relative_to(ROOT / "reports")
        folder.mkdir(parents=True, mode=0o700)
        (folder / "logs").mkdir(mode=0o700)
        compose("up", "--build", "--wait", "--no-deps", "mcp-server")
        compose("cp", "app:/tmp/campusclaw-security-frontend", str(folder / "frontend"))
        (folder / "logs" / "compose.log").write_text(compose("logs", "--no-color"))
        (folder / "logs" / "precheck.log").write_text(output)
        for name in ("app", "mcp-server"):
            image = json.loads(compose("ps", "--format", "json", name))["Image"]
            image_revision = subprocess.check_output(
                [
                    "docker",
                    "image",
                    "inspect",
                    "--format",
                    '{{index .Config.Labels "org.opencontainers.image.revision"}}',
                    image,
                ],
                text=True,
                timeout=30,
            ).strip()
            assert image_revision == version == candidate
            subprocess.run(
                ["docker", "save", "--output", str(folder / f"{name}.tar"), image],
                check=True,
                timeout=180,
            )
        (folder / "revision").write_text(candidate + "\n")
        (folder / "observations.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
        )
    assert all(row[2:] == [401, 1100, True] for row in evidence["anonymous"])
    assert evidence["cross"] == evidence["missing"] and evidence["cross"][:2] == [
        404,
        1300,
    ]
    assert evidence["search_counts"] == [1, 1, 0]
    assert all(row[1:] == [403, 1200, True] for row in evidence["configuration"])
    assert (
        evidence["grading"]["http"] in (404, 405) and evidence["grading"]["unchanged"]
    )


def test_CN_B02_AU_B01_AU_F04_AU_F05_tool_storage(stack):
    compose, _, status, _ = stack
    compose("start", "app")
    assert status("ready")[0] == 200
    assert (
        compose(
            "exec",
            "-T",
            "app",
            "python",
            "-c",
            Path(__file__).with_name("tool_storage_runtime.py").read_text(),
        )
        == "受控工具迁移、约束、恢复与清理通过"
    )


def test_CN_N01_CN_B01_CN_B02_CN_F01_CN_F02_CN_F03_CN_F04_connector_management(stack):
    compose, _, status, _ = stack
    assert status("ready")[0] == 200
    output = compose(
        "exec",
        "-T",
        "app",
        "python",
        "-c",
        Path(__file__).with_name("tool_connectors_runtime.py").read_text(),
    )
    assert output.splitlines()[-1] == "班级连接登记、发现、审阅、断开及并发边界通过"
    assert "synthetic-private-token" not in output and "MCP_SERVICE_TOKEN" not in output


def test_TD_N01_TD_N02_TD_F07_AU_N01_controlled_tool_dialogue(stack):
    compose, _, status, _ = stack
    assert status("ready")[0] == 200
    compose("up", "--build", "--wait", "--no-deps", "mcp-server")
    compose(
        "exec",
        "-T",
        "app",
        "python",
        "-c",
        "from pathlib import Path; import sys; Path('/tmp/session_proxy_worker.py').write_text(sys.argv[1])",
        Path(__file__).with_name("session_proxy_worker.py").read_text(),
    )
    output = compose(
        "exec",
        "-T",
        "-e",
        "PYTHONPATH=/srv/campusclaw:/tmp",
        "app",
        "python",
        "-c",
        Path(__file__).with_name("tool_dialogue_runtime.py").read_text(),
    )
    assert output.splitlines()[-1] == "真实 MCP、会话练习、SSE 顺序和审计投影通过"


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
    compose("stop", "qdrant")
    assert status("degraded")[0] == 200
    verify_teaching_core(compose)
    compose("start", "qdrant")
    assert status("ready")[0] == 200
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


def verify_teaching_core(compose):
    evidence = compose(
        "exec",
        "-T",
        "app",
        "python",
        "-c",
        Path(__file__).with_name("teaching_runtime.py").read_text(),
    )
    assert "TEACHING_RUNTIME_OK" in evidence
    print(evidence)


def test_JB_QB_real_kafka_and_candidate_recovery(stack):
    compose, _, status, _ = stack
    compose("up", "-d", "kafka-topics", teaching=True)
    eventually(
        lambda: (
            compose("logs", "--no-log-prefix", "kafka-topics", teaching=True).count(
                "Created topic"
            )
            == 2
        )
    )
    evidence = verify_teaching_jobs(compose)
    assert "teaching_job_evidence" in evidence
    if os.environ.get("CAMPUSCLAW_REAL_CANDIDATES") == "1":
        assert "teaching_real_gateway_evidence" in evidence
    print(evidence)
    compose("restart", "kafka", teaching=True)
    eventually(
        lambda: (
            compose(
                "exec",
                "-T",
                "kafka",
                "/opt/kafka/bin/kafka-topics.sh",
                "--bootstrap-server",
                "kafka:9092",
                "--list",
                teaching=True,
            ).count("campusclaw.teaching.candidates")
            == 2
        )
    )
    compose("up", "-d", "teaching-relay", "teaching-worker", teaching=True)
    eventually(
        lambda: (
            compose("logs", "--no-log-prefix", "teaching-worker", teaching=True).count(
                '"module": "teaching_processed"'
            )
            >= 20
        )
    )
    compose("stop", "teaching-worker", "teaching-relay", teaching=True)
    workers = list(
        map(
            json.loads,
            compose(
                "ps",
                "-a",
                "--format",
                "json",
                "teaching-worker",
                "teaching-relay",
                teaching=True,
            ).splitlines(),
        )
    )
    assert len(workers) == 2
    assert all(row["ExitCode"] == 0 for row in workers)

    # 5.3: stop only the broker while the core services remain ready.
    compose("stop", "kafka", teaching=True)
    assert compose("ps", "--status", "exited", "-q", "kafka", teaching=True)
    assert status("ready")[0] == 200
    verify_teaching_core(compose)


def verify_teaching_jobs(compose):
    return compose(
        "exec",
        "-T",
        "app",
        "python",
        "-c",
        Path(__file__).with_name("teaching_jobs_runtime.py").read_text(),
    )


def test_JB_F05_mysql_job_transactions_without_broker(stack):
    compose, _, _, _ = stack
    evidence = compose(
        "exec",
        "-T",
        "app",
        "python",
        "-c",
        Path(__file__).with_name("teaching_jobs_runtime.py").read_text(),
        "storage",
    )
    assert evidence.splitlines()[-1] == "teaching_job_storage_ok"


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
