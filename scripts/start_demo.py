"""初始化并启动本机 Docker HTTPS 合成演示；不用于公网发布。"""

import json
import os
import secrets
import ssl
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    os.chdir(ROOT)
    path = ROOT / ".env"
    original = path.read_text() if path.exists() else ""
    values = {}
    for line in original.splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value.strip().strip('"').strip("'")
    defaults = {
        "MYSQL_DATABASE": "campusclaw_test_demo",
        "MYSQL_USER": "campusclaw_app",
        "MYSQL_PASSWORD": secrets.token_hex(24),
        "MYSQL_ROOT_PASSWORD": secrets.token_hex(24),
        "QDRANT_API_KEY": secrets.token_hex(24),
        "CAMPUSCLAW_SEED_PASSWORD": secrets.token_hex(16),
        "APP_PUBLIC_ORIGIN": "https://localhost:8443",
        "APP_HOST_PORT": "8000",
        "DEMO_UID": str(os.getuid()),
        "DEMO_GID": str(os.getgid()),
        "EMBEDDING_BASE_URL": "https://ai-gateway.devops.hello1023.com/v1",
        "EMBEDDING_MODEL": "course-embedding",
        "EMBEDDING_DIM": "2048",
        "CHAT_BASE_URL": "https://ai-gateway.devops.hello1023.com/v1",
        "CHAT_MODEL": "course-chat",
        "RETRIEVAL_MIN_SCORE": "0.449357",
    }
    for key, value in defaults.items():
        if not values.get(key):
            values[key] = value
    # 只针对当前克隆的本地迭代镜像，保留真实提交镜像。
    values["APP_BUILD_REVISION"] = subprocess.check_output(
        ["git", "hash-object", "--stdin"],
        input=f"campusclaw-local-dev:{ROOT}\n",
        text=True,
    ).strip()
    if (
        not values["MYSQL_DATABASE"].startswith("campusclaw_test_")
        or values["APP_PUBLIC_ORIGIN"] != "https://localhost:8443"
        or values["DEMO_UID"] == "0"
    ):
        raise SystemExit("演示只允许专用合成库、本机8443源和非root网关身份")
    # 更新已知键，保留已有值和注释；密钥不经shell、命令行或输出。
    remaining = dict(values)
    lines = []
    for line in original.splitlines():
        key = line.split("=", 1)[0]
        if key in remaining:
            lines.append(key + "=" + remaining.pop(key))
        else:
            lines.append(line)
    lines.extend(key + "=" + value for key, value in remaining.items())
    path.touch(mode=0o600, exist_ok=True)
    path.chmod(0o600)
    path.write_text("\n".join(lines) + "\n")
    env = {**os.environ, **values}
    compose = [
        "docker",
        "compose",
        "-p",
        "campusclaw-demo",
        "-f",
        "docker-compose.yml",
        "-f",
        "docker-compose.demo.yml",
    ]
    output = ROOT / "reports/2026-11-06-index-builds/demo-startup-current.log"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w") as log:

        def run(*args, timeout=300):
            subprocess.run(
                [*compose, *args],
                env=env,
                check=True,
                timeout=timeout,
                stdout=log,
                stderr=log,
            )

        tls = ROOT / "runtime/tls"
        tls.mkdir(parents=True, exist_ok=True)
        certificate, key = tls / "localhost.crt", tls / "localhost.key"
        if not certificate.exists() or not key.exists():
            subprocess.run(
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
                ],
                check=True,
                timeout=30,
                stdout=log,
                stderr=log,
            )
        key.chmod(0o600)
        run("config", "--quiet")
        run("up", "-d", "--wait", "mysql", "qdrant")
        run("build", "app")
        run(
            "run",
            "--rm",
            "--no-deps",
            "app",
            "python",
            "-m",
            "app.auth_admin",
            "upgrade",
        )
        run(
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
        )
        run("up", "-d", "--wait", "app", "gateway")
    context = ssl.create_default_context(cafile=str(certificate))
    for _ in range(30):
        try:
            with urllib.request.urlopen(
                values["APP_PUBLIC_ORIGIN"] + "/health", context=context, timeout=3
            ) as response:
                status = json.load(response)
            if status["status"] == "ready":
                print(
                    "Docker演示已就绪：https://localhost:8443/login；口令见私有.env的CAMPUSCLAW_SEED_PASSWORD"
                )
                return
        except (OSError, ValueError, urllib.error.URLError):
            pass
        time.sleep(1)
    raise SystemExit("HTTPS入口未就绪，检查忽略目录中的演示启动日志")


if __name__ == "__main__":
    main()
