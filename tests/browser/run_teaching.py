"""显式浏览器回归：一次性 MySQL、HTTPS 应用与 Chromium，结束清理。"""

import secrets
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run(*args, capture=False, timeout=420, **options):
    result = subprocess.run(
        args,
        cwd=ROOT,
        check=True,
        timeout=timeout,
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
    browser_image = "campusclaw-teaching-browser:local"
    app_name = f"{project}-app"
    browser_name = f"{project}-chromium"
    origin = f"https://{app_name}:8443"
    password = "Synthetic" + secrets.token_hex(12)
    # BuildKit caches Chromium between runs. Finish downloads before starting MySQL.
    run(
        "docker", "build", "-t", browser_image, str(ROOT / "tests/browser"), timeout=900
    )
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
            run(
                *base,
                "run",
                "-d",
                "--no-deps",
                "--name",
                app_name,
                "-e",
                f"APP_PUBLIC_ORIGIN={origin}",
                "app",
                "python",
                "-c",
                "from app import create_app; create_app().run(host='0.0.0.0', port=8443, ssl_context='adhoc')",
                capture=True,
            )
            browser = (
                "docker",
                "run",
                "--rm",
                "--name",
                browser_name,
                "--network",
                project + "_default",
                "-v",
                f"{ROOT}:/workspace:ro",
                "-e",
                f"CAMPUS_BROWSER_PASSWORD={password}",
                "--entrypoint",
                "sh",
                browser_image,
                "-c",
                "mkdir -p /tmp/teaching-browser\n"
                "chromium --headless --no-sandbox --ignore-certificate-errors --remote-debugging-port=0 --user-data-dir=/tmp/teaching-browser about:blank >/tmp/chrome.log 2>&1 &\n"
                f"node /workspace/tests/browser/teaching.mjs {origin}",
            )
            run(*browser, timeout=90)
            print("TEACHING_BROWSER_RUNTIME_OK")
        finally:
            subprocess.run(
                ["docker", "rm", "-f", browser_name, app_name],
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
