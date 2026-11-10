"""显式浏览器回归：一次性 MySQL、HTTPS 应用与 Chromium，结束清理。"""

import secrets
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run(*args, capture=False, **options):
    result = subprocess.run(
        args,
        cwd=ROOT,
        check=True,
        timeout=420,
        text=True,
        capture_output=capture,
        **options,
    )
    return result.stdout.strip() if capture else ""


def main():
    token = secrets.token_hex(8)
    project = f"campusclaw-teaching-browser-{token}"
    version = secrets.token_hex(20)
    image = f"campusclaw-skeleton:{version}"
    password = "Synthetic" + secrets.token_hex(12)
    with tempfile.TemporaryDirectory(prefix=project + "-") as folder:
        config = Path(folder) / "compose.env"
        config.write_text(
            "\n".join(
                (
                    f"MYSQL_DATABASE=campusclaw_test_{token}",
                    "MYSQL_USER=campusclaw_test",
                    f"MYSQL_PASSWORD={password}",
                    f"MYSQL_ROOT_PASSWORD=Root{secrets.token_hex(12)}",
                    f"QDRANT_API_KEY=Test{secrets.token_hex(12)}",
                    "APP_HOST_PORT=0",
                    f"APP_BUILD_REVISION={version}",
                )
            )
            + "\n"
        )
        base = (
            "docker",
            "compose",
            "--project-name",
            project,
            "--env-file",
            str(config),
            "--file",
            str(ROOT / "docker-compose.yml"),
        )
        app_container = None
        try:
            run(*base, "up", "-d", "mysql", capture=True)
            for _ in range(60):
                if "healthy" in run(
                    *base, "ps", "--format", "json", "mysql", capture=True
                ):
                    break
                time.sleep(2)
            else:
                raise RuntimeError("合成 MySQL 未就绪")
            run(*base, "build", "app", capture=True)
            run(
                *base,
                "run",
                "--rm",
                "--no-deps",
                "app",
                "python",
                "-m",
                "app.auth_admin",
                "upgrade",
                capture=True,
            )
            run(
                *base,
                "run",
                "--rm",
                "--no-deps",
                "-e",
                "CAMPUSCLAW_ISOLATED_DATABASE=1",
                "-e",
                f"CAMPUSCLAW_SEED_PASSWORD={password}",
                "app",
                "python",
                "-m",
                "app.auth_admin",
                "seed",
                capture=True,
            )
            app_container = run(
                *base,
                "run",
                "-d",
                "--no-deps",
                "--name",
                "teaching-ui-app",
                "-e",
                "APP_PUBLIC_ORIGIN=https://teaching-ui-app:8443",
                "app",
                "python",
                "-c",
                "from app import create_app; create_app().run(host='0.0.0.0', port=8443, ssl_context='adhoc')",
                capture=True,
            ).splitlines()[-1]
            browser = (
                "docker",
                "run",
                "--rm",
                "--network",
                project + "_default",
                "-v",
                f"{ROOT}:/workspace:ro",
                "-e",
                f"CAMPUS_BROWSER_PASSWORD={password}",
                "--entrypoint",
                "sh",
                "node:22-alpine@sha256:0e1754758c2df4cfa3e68d59e2e1b7374bb7fd9ea6328eaaacf15cc934af8202",
                "-c",
                "apk add --no-cache chromium >/dev/null\n"
                "mkdir -p /tmp/teaching-browser\n"
                "chromium --headless --no-sandbox --ignore-certificate-errors --remote-debugging-port=0 --user-data-dir=/tmp/teaching-browser about:blank >/tmp/chrome.log 2>&1 &\n"
                "node /workspace/tests/browser/teaching.mjs https://teaching-ui-app:8443",
            )
            # 浏览器容器的包安装和启动在同一个隔离网络内完成。
            run(*browser)
            print("TEACHING_BROWSER_RUNTIME_OK")
        finally:
            if app_container:
                subprocess.run(
                    ["docker", "rm", "-f", app_container],
                    capture_output=True,
                    check=False,
                )
            subprocess.run(
                [*base, "down", "-v", "--remove-orphans"],
                capture_output=True,
                check=False,
            )
            subprocess.run(
                ["docker", "image", "rm", image], capture_output=True, check=False
            )


if __name__ == "__main__":
    main()
