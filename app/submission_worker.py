"""MySQL 正式提交任务 worker。"""

import os
import signal
import threading
from pathlib import Path

from app.adapters.database import DatabaseError, mysql_engine
from app.adapters.teaching_repository import TeachingRepository
from app.config import Settings
from app.observability import log_event
from app.services.submission_jobs import SubmissionJobWorker


def main():
    settings = Settings.load(os.environ, Path(__file__).with_name("BUILD_VERSION"))
    engine = mysql_engine(
        host=settings.mysql_host,
        port=settings.mysql_port,
        database=settings.mysql_database,
        user=settings.mysql_user,
        password=settings.mysql_password,
    )
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
    main()
