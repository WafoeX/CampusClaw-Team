"""MySQL 正式提交任务 worker。"""

import os
import signal
import sys
import threading
from pathlib import Path

from sqlalchemy import text

from app.adapters.database import DatabaseError, mysql_engine
from app.adapters.teaching_repository import TeachingRepository
from app.config import Settings
from app.observability import log_event
from app.services.submission_jobs import SubmissionJobWorker


def configured_engine():
    settings = Settings.load(os.environ, Path(__file__).with_name("BUILD_VERSION"))
    return settings, mysql_engine(
        host=settings.mysql_host,
        port=settings.mysql_port,
        database=settings.mysql_database,
        user=settings.mysql_user,
        password=settings.mysql_password,
    )


def worker_ready(engine):
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


def healthcheck():
    _, engine = configured_engine()
    try:
        worker_ready(engine)
    finally:
        engine.dispose()


def main():
    settings, engine = configured_engine()
    repository = TeachingRepository(engine)
    worker = SubmissionJobWorker(repository)
    stopping = threading.Event()

    def stop(*_):
        stopping.set()

    for item in (signal.SIGINT, signal.SIGTERM):
        signal.signal(item, stop)
    delay = 1
    try:
        while not stopping.is_set():
            try:
                worked = worker.run_once()
                delay = 1
                if not worked:
                    log_event(
                        "submission_backlog",
                        settings.version,
                        **repository.submission_job_metrics(),
                    )
                    stopping.wait(0.5)
            except DatabaseError as error:
                log_event(
                    "submission_dependency",
                    settings.version,
                    reason=type(error).__name__,
                )
                stopping.wait(delay)
                delay = min(delay * 2, 15)
    finally:
        engine.dispose()


if __name__ == "__main__":
    if sys.argv[1:] == ["--healthcheck"]:
        healthcheck()
    elif sys.argv[1:]:
        raise SystemExit("submission-worker 参数无效")
    else:
        main()
