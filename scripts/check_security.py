"""扫描隔离候选的 Git、工作文件、前端、运行日志、镜像及锁定依赖。"""

import argparse
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGE_NAMES = ("app.tar", "mcp-server.tar")
FILES = {
    "frontend": (
        "login.html",
        "materials.html",
        "quizzes.html",
        "swagger.html",
        "openapi.json",
    ),
    "logs": ("compose.log", "precheck.log"),
}


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, timeout=30)


def mount(source, target, *, readonly=True):
    options = f"type=bind,src={source},dst={target}"
    return ["--mount", options + (",readonly" if readonly else "")]


def docker_json(image, mounts, args, output):
    output.unlink(missing_ok=True)
    try:
        completed = subprocess.run(
            ["docker", "run", "--rm", *mounts, image, *args],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=420,
            check=False,
        )
        if completed.returncode:
            return completed.returncode, None
        return 0, json.loads(output.read_text())
    except (OSError, ValueError, subprocess.SubprocessError):
        return 2, None


def public_result(name, code, **counts):
    result = {"scope": name, "exit": code, **counts}
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return code


def gitleaks(image, name, source, output, *, history=False):
    mode = "git" if history else "dir"
    options = ["--log-opts=--all"] if history else []
    mounts = mount(source, "/asset") + mount(output.parent, "/out", readonly=False)
    code, rows = docker_json(
        image,
        mounts,
        [
            mode,
            "--no-banner",
            "--redact=100",
            "--exit-code=0",
            "--report-format=json",
            f"--report-path=/out/{output.name}",
            *options,
            "/asset",
        ],
        output,
    )
    if code or not isinstance(rows, list):
        return public_result(name, 2, tool_exit=code)
    return public_result(name, int(bool(rows)), secrets=len(rows))


def trivy(image, name, source, cache, output, *, archive=False):
    mounts = mount(source, "/asset") + mount(cache, "/cache", readonly=False)
    mounts += mount(output.parent, "/out", readonly=False)
    target = (
        ["--input", "/asset", "--image-config-scanners", "secret"]
        if archive
        else ["--include-dev-deps", "/asset"]
    )
    code, report = docker_json(
        image,
        mounts,
        [
            "image" if archive else "fs",
            "--cache-dir=/cache",
            "--no-progress",
            "--scanners=" + ("secret" if archive else "vuln"),
            "--timeout=2m",
            "--format=json",
            f"--output=/out/{output.name}",
            *target,
        ],
        output,
    )
    if code or not isinstance(report, dict) or not report.get("ArtifactName"):
        return public_result(name, 2, tool_exit=code)
    rows = report.get("Results", [])
    if not isinstance(rows, list) or (not archive and not rows):
        return public_result(name, 2)
    counts = {"high": 0, "critical": 0, "secrets": 0}
    for row in rows:
        for vulnerability in row.get("Vulnerabilities") or ():
            severity = vulnerability["Severity"].lower()
            if severity in ("high", "critical"):
                counts[severity] += 1
        counts["secrets"] += len(row.get("Secrets") or ())
    blocking = any(counts.values())
    if archive:
        return public_result(name, int(blocking), secrets=counts["secrets"])
    metadata = json.loads((cache / "db" / "metadata.json").read_text())
    if datetime.fromisoformat(metadata["NextUpdate"]) <= datetime.now(UTC):
        return public_result(name, 2, reason="database_expired")
    return public_result(
        name,
        int(blocking),
        high=counts["high"],
        critical=counts["critical"],
        database_schema=metadata["Version"],
        database_updated=metadata["UpdatedAt"],
    )


def working_files(destination):
    files = git("ls-files", "--cached", "--others", "--exclude-standard", "-z")
    destination.mkdir()
    for entry in files.split(b"\0"):
        if not entry:
            continue
        relative = Path(os.fsdecode(entry))
        source = ROOT / relative
        if source.is_file() and source.resolve() == source:
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)


def image_matches(path, revision):
    with tarfile.open(path, "r:") as archive:
        manifest = json.load(archive.extractfile("manifest.json"))
        if len(manifest) != 1:
            return False
        config = json.load(archive.extractfile(manifest[0]["Config"]))
        return (
            config["config"]["Labels"]["org.opencontainers.image.revision"] == revision
        )


def run_checks(args, scratch):
    output = scratch / "result.json"
    assets = args.assets.resolve()
    cache = args.cache.resolve()
    cache.mkdir(parents=True, exist_ok=True)
    revision = git("rev-parse", "HEAD").decode().strip()
    print(
        json.dumps(
            {
                "revision": revision,
                "candidate": args.candidate,
                "reachable_commits": int(git("rev-list", "--all", "--count")),
                "gitleaks": args.gitleaks,
                "trivy": args.trivy,
            }
        ),
        flush=True,
    )
    try:
        candidate = bool(re.fullmatch(r"[0-9a-f]{40}", args.candidate)) and (
            (assets / "revision").read_text().strip() == args.candidate
        )
        git("cat-file", "-e", args.candidate + "^{commit}")
    except (OSError, subprocess.SubprocessError):
        candidate = False

    def history():
        if git("rev-parse", "--is-shallow-repository").strip() != b"false":
            return public_result("history", 2)
        bare = scratch / "history.git"
        # 复制本地可达引用，避免容器读取用户私有环境或链接工作树的指针。
        subprocess.run(
            ["git", "clone", "--mirror", "--no-local", "--quiet", str(ROOT), str(bare)],
            check=True,
            timeout=90,
        )
        return gitleaks(args.gitleaks, "history", bare, output, history=True)

    def worktree():
        folder = scratch / "worktree"
        working_files(folder)
        return gitleaks(args.gitleaks, "worktree", folder, output)

    def directory(name):
        path = assets / name
        if (
            not candidate
            or path.is_symlink()
            or not all(
                (path / filename).is_file()
                and not (path / filename).is_symlink()
                and (path / filename).stat().st_size
                for filename in FILES[name]
            )
        ):
            return public_result(name, 2)
        return gitleaks(args.gitleaks, name, path, output)

    def locked():
        if not re.fullmatch(r"[0-9a-f]{40}", args.candidate):
            return public_result("dependencies", 2)
        lock = scratch / "locked"
        lock.mkdir()
        (lock / "uv.lock").write_bytes(git("show", args.candidate + ":uv.lock"))
        return trivy(args.trivy, "dependencies", lock, cache, output)

    def image(name):
        path = assets / name
        if (
            not candidate
            or not path.is_file()
            or path.is_symlink()
            or not path.stat().st_size
            or not image_matches(path, args.candidate)
        ):
            return public_result(name, 2)
        return trivy(args.trivy, name, path, cache, output, archive=True)

    checks = [
        ("history", history),
        ("worktree", worktree),
        ("frontend", lambda: directory("frontend")),
        ("logs", lambda: directory("logs")),
        ("dependencies", locked),
        *[(name, lambda name=name: image(name)) for name in IMAGE_NAMES],
    ]
    results = []
    for name, check in checks:
        try:
            results.append(check())
        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            subprocess.SubprocessError,
            tarfile.TarError,
        ):
            results.append(public_result(name, 2))
    return int(any(results))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--gitleaks", required=True)
    parser.add_argument("--trivy", required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="campusclaw-security-") as temporary:
        return run_checks(args, Path(temporary))


if __name__ == "__main__":
    raise SystemExit(main())
