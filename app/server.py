"""Run the WSGI worker and withdraw readiness before graceful shutdown."""

import argparse
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

from app import VERSION_FILE, create_app
from app.config import ConfigError, Settings
from app.observability import log_event


def load_worker():
    marker = Path(os.environ["CAMPUSCLAW_DRAIN_MARKER"])
    return create_app(draining=marker.exists)


def run(bind):
    try:
        settings = Settings.load(os.environ, VERSION_FILE)
    except ConfigError as error:
        log_event("startup", None, level="ERROR", invalid_key=str(error))
        return 1

    stopping = False

    def stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    with tempfile.TemporaryDirectory(prefix="campusclaw-drain-") as directory:
        marker = Path(directory) / "draining"
        child = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "gunicorn",
                "--config",
                "python:app.wsgi_config",
                "--bind",
                bind,
                "app.server:load_worker()",
            ],
            env={
                **os.environ,
                "CAMPUSCLAW_DRAIN_MARKER": str(marker),
                "GUNICORN_CMD_ARGS": "",
            },
            start_new_session=True,
        )
        log_event("startup", settings.version, event="starting")
        while not stopping:
            try:
                result = child.wait(timeout=0.1)
            except subprocess.TimeoutExpired:
                continue
            log_event(
                "shutdown", settings.version, event="worker_exited", exit_code=result
            )
            return result if result >= 0 else 128 - result

        marker.touch()
        log_event("shutdown", settings.version, event="draining")
        forced = False
        try:
            # Keep the probe reachable briefly so readiness withdrawal is observable.
            child.wait(timeout=1)
        except subprocess.TimeoutExpired:
            child.terminate()
            try:
                child.wait(timeout=28)
            except subprocess.TimeoutExpired:
                forced = True
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait()
        log_event("shutdown", settings.version, event="stopped", forced=forced)
        return int(forced)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bind", default="0.0.0.0:8080")
    return run(parser.parse_args().bind)
