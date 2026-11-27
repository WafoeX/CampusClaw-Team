"""完整的本机预验收环境；只使用专用合成库与回环端口。"""

import argparse
import ast
import ipaddress
import json
import os
import secrets
import socket
import ssl
import subprocess
import urllib.request
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

from scripts.dependency_sources import SOURCES, mirrored_dependencies
from scripts.smoke_acceptance import smoke

ROOT = Path(__file__).resolve().parents[1]
MODEL_KEYS = (
    "CHAT_BASE_URL",
    "CHAT_MODEL",
    "CHAT_API_KEY",
    "EMBEDDING_BASE_URL",
    "EMBEDDING_MODEL",
    "EMBEDDING_DIM",
    "EMBEDDING_API_KEY",
    "RETRIEVAL_MIN_SCORE",
)
ORIGIN = "https://localhost:8444"
REQUIRED = {
    "app",
    "submission-worker",
    "mysql",
    "qdrant",
    "gateway",
    "mcp-server",
    "kafka",
    "teaching-relay",
    "teaching-worker",
}


def private_json(path, value):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as output:
        json.dump(value, output)
    path.chmod(0o600)


def model_values(path):
    result = {}
    if path.is_file():
        for line in path.read_text().splitlines():
            key, separator, raw = line.partition("=")
            key = key.strip()
            if not separator or key not in MODEL_KEYS:
                continue
            value = raw.strip()
            if value.startswith(("'", '"')):
                try:
                    value = ast.literal_eval(value)
                except (ValueError, SyntaxError):
                    raise ValueError(f"模型配置格式无效：{key}") from None
            if not isinstance(value, str) or any(char in value for char in "\r\n\x00"):
                raise ValueError(f"模型配置格式无效：{key}")
            if value:
                result[key] = value
    return result


def configuration(root, previous, models, revision):
    suffix = sha256(str(root.resolve()).encode()).hexdigest()[:8]
    project = f"campusclaw-acceptance-{suffix}"
    values = dict(previous)
    defaults = {
        "MYSQL_HOST": "mysql",
        "MYSQL_PORT": "3306",
        "MYSQL_DATABASE": f"campusclaw_test_acceptance_{suffix}",
        "MYSQL_USER": "campusclaw_app",
        "MYSQL_PASSWORD": secrets.token_hex(24),
        "MYSQL_ROOT_PASSWORD": secrets.token_hex(24),
        "QDRANT_URL": "http://qdrant:6333",
        "QDRANT_API_KEY": secrets.token_hex(24),
        "CAMPUSCLAW_SEED_PASSWORD": secrets.token_hex(16),
        "MCP_SERVICE_TOKEN": secrets.token_hex(32),
        "TOOL_PRACTICE_SIGNING_KEY": secrets.token_hex(32),
    }
    for key, value in defaults.items():
        values.setdefault(key, value)
    if any(
        values[key] != defaults[key]
        for key in (
            "MYSQL_HOST",
            "MYSQL_PORT",
            "MYSQL_DATABASE",
            "MYSQL_USER",
            "QDRANT_URL",
        )
    ):
        raise ValueError("预验收配置必须使用本克隆的专用合成库和内部服务")
    for key in MODEL_KEYS:
        values.pop(key, None)
    values.update(models)
    values.update(
        APP_PUBLIC_ORIGIN=ORIGIN,
        APP_HOST_PORT="18000",
        APP_BUILD_REVISION=revision,
        DEMO_UID=str(os.getuid()),
        DEMO_GID=str(os.getgid()),
        TEACHING_JOBS_ENABLED="1",
    )
    if values["DEMO_UID"] == "0":
        raise ValueError("本机验收网关必须使用非 root 身份")
    if any(
        not isinstance(value, str) or any(char in value for char in "\r\n\x00")
        for value in values.values()
    ):
        raise ValueError("私有配置值必须是单行字符串")
    return project, values


def rows(text):
    return (
        json.loads(text)
        if text.lstrip().startswith("[")
        else [json.loads(line) for line in text.splitlines() if line.strip()]
    )


def gateway_service(source, tls):
    gateway = deepcopy(source)
    gateway["ports"] = ["127.0.0.1:8444:8443"]
    for mount in gateway["volumes"]:
        if mount["target"] == "/etc/campusclaw/tls":
            mount["source"] = str(tls)
    return gateway


def inspect_status(compose, run, certificate, revision):
    services = {
        row["Service"]: {"state": row["State"], "health": row.get("Health", "")}
        for row in rows(run([*compose, "ps", "--format", "json"], capture=True))
    }
    if not all(services.get(name, {}).get("state") == "running" for name in REQUIRED):
        raise ValueError("预验收必需服务未全部运行")
    probes = {}
    context = ssl.create_default_context(cafile=str(certificate))
    for name in ("live", "health"):
        with urllib.request.urlopen(
            f"{ORIGIN}/{name}", context=context, timeout=5
        ) as response:
            probes[name] = json.load(response)
    if (
        probes["live"]["status"] != "alive"
        or probes["health"]["status"] != "ready"
        or probes["health"]["version"] != revision
    ):
        raise ValueError("双探针或实际运行版本未满足预验收要求")
    return {
        "origin": ORIGIN,
        "revision": revision,
        "services": services,
        "probes": probes,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=("start", "status", "smoke", "stop"),
        nargs="?",
        default="start",
    )
    parser.add_argument("--mirror-host", help="显式依赖来源主机，保持全部摘要")
    args = parser.parse_args()
    state = ROOT / "runtime/acceptance"
    state.mkdir(parents=True, mode=0o700, exist_ok=True)
    state.chmod(0o700)
    config_path = state / "config.json"
    previous = json.loads(config_path.read_text()) if config_path.exists() else {}
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    models = (
        model_values(ROOT / ".env")
        if args.action == "start"
        else {key: previous[key] for key in MODEL_KEYS if key in previous}
    )
    if args.action != "start":
        revision = previous.get("APP_BUILD_REVISION", revision)
    project, values = configuration(ROOT, previous, models, revision)
    if args.action != "start" and not config_path.exists():
        raise SystemExit("尚无本克隆的预验收配置")
    # 配置通过环境注入，空 env 文件避免读取其他项目的默认 .env。
    env_path = state / "compose.env"
    env_path.touch(mode=0o600, exist_ok=True)
    env_path.chmod(0o600)
    env = {
        key: value
        for key, value in os.environ.items()
        if key
        not in {
            "COMPOSE_FILE",
            "COMPOSE_PROJECT_NAME",
            "COMPOSE_ENV_FILES",
            "DOCKER_HOST",
            "DOCKER_CONTEXT",
        }
    } | values
    compose = [
        "docker",
        "compose",
        "--project-name",
        project,
        "--env-file",
        str(env_path),
    ]
    for filename in (
        "docker-compose.yml",
        "docker-compose.teaching.yml",
    ):
        compose.extend(("--file", str(ROOT / filename)))
    compose.extend(("--profile", "tools", "--profile", "teaching"))
    overlay = state / "compose.json"
    tls = state / "tls"
    tls.mkdir(mode=0o700, exist_ok=True)
    with (state / "startup.log").open("w") as log:
        (state / "startup.log").chmod(0o600)

        def run(command, *, capture=False, timeout=600):
            result = subprocess.run(
                command,
                cwd=ROOT,
                env=env,
                check=True,
                timeout=timeout,
                text=True,
                stdout=subprocess.PIPE if capture else log,
                stderr=log,
            )
            return result.stdout.strip() if capture else ""

        endpoint = run(
            ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
            capture=True,
        )
        if not endpoint.startswith("unix://"):
            raise ValueError("预验收仅允许本机 Docker Unix socket")
        demo = json.loads(
            run(
                [
                    *compose,
                    "--file",
                    str(ROOT / "docker-compose.demo.yml"),
                    "config",
                    "--format",
                    "json",
                ],
                capture=True,
            )
        )
        private_json(
            overlay,
            {
                "services": {
                    "gateway": gateway_service(demo["services"]["gateway"], tls)
                }
            },
        )
        compose.extend(("--file", str(overlay)))
        if args.mirror_host:
            configured = json.loads(
                run([*compose, "config", "--format", "json"], capture=True)
            )
            image_overlay = state / "sources.json"
            private_json(
                image_overlay,
                mirrored_dependencies(configured, args.mirror_host, tuple(SOURCES)),
            )
            compose.extend(("--file", str(image_overlay)))
        if args.action == "stop":
            run([*compose, "down", "--remove-orphans"])
            print("本克隆预验收环境已停止，数据卷与私有配置保留")
            return
        if args.action == "start":
            if subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=ROOT, text=True
            ).strip():
                raise ValueError("预验收启动需要干净源码，请先提交当前改动")
            if not run([*compose, "ps", "-q"], capture=True):
                for port in (18000, 8444):
                    with socket.socket() as probe:
                        probe.bind(("127.0.0.1", port))
            private_json(config_path, values)
            run([*compose, "up", "-d", "--wait", "mysql", "qdrant"])
            networks = json.loads(
                run(
                    ["docker", "network", "inspect", project + "_default"], capture=True
                )
            )
            network = networks[0]["IPAM"]["Config"][0]["Subnet"]
            if not ipaddress.ip_network(network).is_private:
                raise ValueError("MCP 仅允许专用私有网络")
            values["MCP_SERVICE_NETWORK"] = network
            env["MCP_SERVICE_NETWORK"] = network
            private_json(config_path, values)
            run([*compose, "build", "app", "mcp-server"])
            run(
                [
                    *compose,
                    "run",
                    "--rm",
                    "--no-deps",
                    "app",
                    "python",
                    "-m",
                    "app.auth_admin",
                    "upgrade",
                ]
            )
            run(
                [
                    *compose,
                    "run",
                    "--rm",
                    "--no-deps",
                    "-e",
                    "CAMPUSCLAW_ISOLATED_DATABASE=1",
                    "-e",
                    "CAMPUSCLAW_SEED_PASSWORD",
                    "app",
                    "python",
                    "-m",
                    "app.auth_admin",
                    "seed",
                ]
            )
            certificate, key = tls / "localhost.crt", tls / "localhost.key"
            if not certificate.exists() or not key.exists():
                run(
                    [
                        "openssl",
                        "req",
                        "-x509",
                        "-newkey",
                        "rsa:2048",
                        "-nodes",
                        "-keyout",
                        str(key),
                        "-out",
                        str(certificate),
                        "-days",
                        "30",
                        "-subj",
                        "/CN=localhost",
                        "-addext",
                        "subjectAltName=DNS:localhost,IP:127.0.0.1",
                    ]
                )
                key.chmod(0o600)
            run([*compose, "up", "-d", "--wait"])
        report = inspect_status(
            compose, run, tls / "localhost.crt", values["APP_BUILD_REVISION"]
        )
        report["models_configured"] = {
            "chat": bool(values.get("CHAT_API_KEY")),
            "embedding": bool(values.get("EMBEDDING_API_KEY")),
        }
        private_json(state / "status.json", report)
        if args.action == "smoke":
            result = smoke(state, values)
            private_json(state / "smoke.json", result)
            print(
                json.dumps(
                    {
                        "smoke": "passed",
                        "revision": result["revision"],
                        "requests": result["requests"],
                        "persisted_average_score": result["persisted_average_score"],
                        "real_model_evaluation": result["real_model_evaluation"],
                        "human_acceptance": result["human_acceptance"],
                    },
                    ensure_ascii=False,
                )
            )
        print(json.dumps(report, ensure_ascii=False))
        print(
            "演示账号口令仅见 runtime/acceptance/config.json 的 CAMPUSCLAW_SEED_PASSWORD；正式验收尚未完成"
        )


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise SystemExit(
            f"预验收操作失败（{type(error).__name__}）；检查本克隆 runtime/acceptance/startup.log，勿公开私有配置"
        ) from None
