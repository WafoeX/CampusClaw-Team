"""显式浏览器回归：一次性 MySQL、HTTPS 应用与 Chromium，结束清理。"""

import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.dependency_sources import mirrored_dependencies  # noqa: E402


def run(*args, capture=False, timeout=420, **options):
    try:
        result = subprocess.run(
            args,
            cwd=ROOT,
            check=True,
            timeout=timeout,
            text=True,
            capture_output=capture,
            **options,
        )
    except subprocess.CalledProcessError as error:
        if capture:
            print(error.stdout or "", end="")
            print(error.stderr or "", end="", file=sys.stderr)
        raise
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
        control = Path(folder) / "control"
        control.mkdir(mode=0o777)
        control.chmod(0o777)  # 临时合成标识闸门，供两个容器用户交接；不写凭据。
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
        base = [
            "docker",
            "compose",
            "--project-name",
            project,
            "--env-file",
            str(config),
            "--file",
            str(ROOT / "docker-compose.yml"),
        ]
        if mirror := os.environ.get("CAMPUSCLAW_TEST_DOCKER_MIRROR"):
            configuration = json.loads(
                run(*base, "config", "--format", "json", capture=True)
            )
            source_overlay = Path(folder) / "dependency-sources.json"
            source_overlay.write_text(
                json.dumps(mirrored_dependencies(configuration, mirror, ("mysql",)))
            )
            base.extend(("--file", str(source_overlay)))
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
                "CAMPUSCLAW_SEED_PASSWORD",
                "app",
                "python",
                "-m",
                "app.auth_admin",
                "seed",
                capture=True,
                env={**os.environ, "CAMPUSCLAW_SEED_PASSWORD": password},
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
                "-v",
                f"{control}:/tmp/browser-control",
                "-v",
                f"{ROOT / 'tests/browser/teaching_app.py'}:/tmp/teaching_app.py:ro",
                "app",
                "python",
                "-c",
                "import runpy; runpy.run_path('/tmp/teaching_app.py', run_name='__main__')",
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
                "-v",
                f"{control}:/tmp/browser-control",
                "-e",
                "CAMPUS_BROWSER_PASSWORD",
                "--entrypoint",
                "sh",
                browser_image,
                "-c",
                "mkdir -p /tmp/teaching-browser\n"
                "chromium --headless --no-sandbox --ignore-certificate-errors --remote-debugging-port=0 --user-data-dir=/tmp/teaching-browser about:blank >/tmp/chrome.log 2>&1 &\n"
                f"node /workspace/tests/browser/teaching.mjs {origin}",
            )
            run(
                *browser,
                timeout=90,
                env={**os.environ, "CAMPUS_BROWSER_PASSWORD": password},
            )
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
