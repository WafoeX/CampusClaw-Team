"""Scan reachable Git history and working files eligible for version control."""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def scan(image, folder, mode, *options):
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--mount",
            f"type=bind,src={folder},dst=/repo,readonly",
            "--env",
            "GIT_CONFIG_COUNT=1",
            "--env",
            "GIT_CONFIG_KEY_0=safe.directory",
            "--env",
            "GIT_CONFIG_VALUE_0=/repo",
            image,
            mode,
            "--no-banner",
            "--redact",
            *options,
            "/repo",
        ],
        check=True,
    )


def main():
    image = sys.argv[1]
    root = Path(__file__).resolve().parents[1]
    entries = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
    )
    scan(image, root, "git", "--log-opts=--all")
    with tempfile.TemporaryDirectory(prefix="campusclaw-secrets-") as directory:
        target = Path(directory)
        for entry in entries.split(b"\0"):
            if not entry:
                continue
            relative = Path(entry.decode())
            source = root / relative
            if source.is_file() and not source.is_symlink():
                output = target / relative
                output.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, output)
        scan(image, target, "dir")


if __name__ == "__main__":
    main()
