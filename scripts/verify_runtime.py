"""Collect a small, credential-free cold-start record from local probes."""

import argparse
import json
import platform
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]


class VerificationError(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(port, path, method="GET"):
    opener = build_opener(ProxyHandler({}), NoRedirect())
    try:
        response = opener.open(
            Request(f"http://127.0.0.1:{port}{path}", method=method), timeout=3
        )
    except HTTPError as error:
        response = error
    with response:
        body = response.read(65537)
        if len(body) > 65536:
            raise VerificationError("探针响应超过大小限制")
        return response.status, body, response.headers


def inspect_probes(port, revision):
    observations = {}
    for path in ("/live", "/health"):
        status, raw, headers = request(port, path)
        if status != 200:
            raise VerificationError("探针尚未就绪")
        try:
            body = json.loads(raw)
        except (ValueError, UnicodeError) as error:
            raise VerificationError("探针未返回合法 JSON") from error
        if not isinstance(body, dict):
            raise VerificationError("探针响应结构错误")
        request_id = body.get("request_id")
        if (
            not isinstance(request_id, str)
            or not re.fullmatch(r"[0-9a-f]{32}", request_id)
            or headers.get("X-Request-ID") != request_id
            or headers.get("Cache-Control") != "no-store"
            or headers.get_content_type() != "application/json"
        ):
            raise VerificationError("探针响应头或请求标识不匹配")
        if path == "/live":
            if body.get("status") != "alive":
                raise VerificationError("进程存活状态错误")
        else:
            if body.get("version") != revision:
                raise VerificationError("运行版本与约定提交不一致")
            if body.get("status") != "ready" or body.get("dependencies") != {
                "mysql": "ready",
                "qdrant": "ready",
            }:
                raise VerificationError("两项依赖尚未全部就绪")
            stamp = body.get("time")
            try:
                if not isinstance(stamp, str) or not stamp.endswith("Z"):
                    raise ValueError
                datetime.fromisoformat(stamp)
            except ValueError as error:
                raise VerificationError("探针时间不是 UTC 时间") from error
        head_status, head_body, head_headers = request(port, path, "HEAD")
        if (
            head_status != status
            or head_body
            or head_headers.get_content_type() != "application/json"
            or head_headers.get("Cache-Control") != "no-store"
            or not re.fullmatch(r"[0-9a-f]{32}", head_headers.get("X-Request-ID", ""))
        ):
            raise VerificationError("HEAD 探针契约错误")
        observations[path] = {"http_status": status, "request_id": request_id}
    return observations


def command(*args):
    return subprocess.check_output(
        args, cwd=ROOT, text=True, stderr=subprocess.DEVNULL, timeout=15
    ).strip()


def collect(port):
    revision = command("git", "rev-parse", "HEAD")
    if command("git", "status", "--porcelain", "--untracked-files=normal"):
        raise VerificationError("请先提交或清理工作区，再按同一提交冷启动")
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise VerificationError("源码提交标识无效")
    observations = inspect_probes(port, revision)
    return {
        "result": "passed",
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "revision": revision,
        "worktree_clean": True,
        "system": {"os": platform.system(), "release": platform.release()},
        "docker_version": command(
            "docker", "version", "--format", "{{.Server.Version}}"
        ),
        "compose_version": command("docker", "compose", "version", "--short"),
        "probes": observations,
        "dependencies": {"mysql": "ready", "qdrant": "ready"},
        "review": "待成员填写实名、实际启动步骤、遇阻复测及交叉评审",
    }


def main():
    parser = argparse.ArgumentParser(description="核验本机冷启动并生成脱敏记录")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("端口须为 1–65535")
    started = time.monotonic()
    try:
        report = collect(args.port)
        report["verification_seconds"] = round(time.monotonic() - started, 3)
        output = args.output or ROOT / "reports" / "cold-start.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        # Use exclusive creation so a failed rerun cannot leave an old success as new evidence.
        with output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    except VerificationError as error:
        print(f"冷启动核验失败：{error}。", file=sys.stderr)
        return 1
    except (OSError, ValueError, subprocess.SubprocessError):
        print(
            "冷启动核验失败：检查就绪、版本、干净工作区及输出路径；不覆盖旧报告。",
            file=sys.stderr,
        )
        return 1
    print(f"冷启动核验通过，脱敏记录：{output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
