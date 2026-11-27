"""浏览器专用装配：真实 MySQL、固定模型、文件闸门控制任务推进。"""

import json
import os
import threading
import time
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, insert, select, update

from app import create_app
from app.adapters.database import DatabaseError, mysql_engine
from app.adapters.index_schema_v5 import builds, chunks, materials
from app.adapters.material_schema_v2 import bodies
from app.adapters.retrieval_repository import RetrievalRepository
from app.adapters.teaching_jobs import TeachingJobs
from app.adapters.teaching_repository import TeachingRepository
from app.adapters.teaching_schema_v12 import generated_questions, job_results, outbox
from app.config import Settings
from app.services.submission_jobs import SubmissionJobWorker
from app.services.teaching_candidates import CandidateJobs
from app.teaching_job_contract import Event

CONTROL = Path("/tmp/browser-control")
QUOTE = "串联电路各处电流相等。"


def wait_file(name):
    for _ in range(900):
        path = CONTROL / name
        if path.exists():
            return path.read_text()
        time.sleep(0.1)
    raise AssertionError("浏览器任务闸门超时：" + name)


class Model:
    def complete_once(self, *_args):
        return {
            "insufficient": False,
            "questions": [
                {
                    "kind": "true_false",
                    "stem": QUOTE,
                    "options": ["正确", "错误"],
                    "answer": "true",
                    "explanation": "资料说明" + QUOTE,
                    "evidence": 1,
                    "quote": QUOTE,
                }
            ],
        }


def coordinate(repository, service):
    try:
        source = wait_file("source")
        # 与既有真实依赖回归相同，只准备一份合成的已发布关键词切片。
        with repository.transaction() as connection:
            row = (
                connection.execute(select(materials).where(materials.c.id == source))
                .mappings()
                .one()
            )
            assert (
                connection.scalar(
                    select(bodies.c.content).where(bodies.c.material_id == source)
                ).decode()
                == QUOTE
            )
            now = repository.now(connection)
            pins = {
                "class_id": row["class_id"],
                "material_id": source,
                "source_version": row["content_version"],
                "index_version": 1,
                "index_config_version": "synthetic-browser-v1",
            }
            connection.execute(
                insert(builds).values(
                    **pins,
                    id=str(uuid4()),
                    creator_id=row["creator_id"],
                    mode="auto",
                    window_size=600,
                    overlap=100,
                    status="published",
                    stage="published",
                    created_at=now,
                    updated_at=now,
                )
            )
            connection.execute(
                insert(chunks).values(
                    **pins,
                    id=str(uuid4()),
                    ordinal=0,
                    start_offset=0,
                    end_offset=len(QUOTE),
                    content=QUOTE,
                )
            )
            connection.execute(
                update(materials)
                .where(materials.c.id == source)
                .values(active_index_version=1)
            )
        (CONTROL / "indexed").write_text("ok")
        job_id = wait_file("claim")
        with repository.engine.connect() as connection:
            job = repository.job(connection, job_id)
        claim = repository.claim_job(
            Event(job["event_id"], job_id, job["generation"], job["trace_id"])
        )
        assert claim is not None
        assert wait_file("complete") == job_id
        assert service.complete(claim, drafts=service.generate(claim))
        with repository.engine.connect() as connection:
            for table in (outbox, job_results, generated_questions):
                assert (
                    connection.scalar(
                        select(func.count())
                        .select_from(table)
                        .where(table.c.job_id == job_id)
                    )
                    == 1
                )
            assert (
                repository.claim_job(
                    Event(job["event_id"], job_id, job["generation"], job["trace_id"])
                )
                is None
            )
        (CONTROL / "verified").write_text(
            json.dumps({"task_id": job_id, "outbox": 1, "results": 1, "drafts": 1})
        )
    except Exception:
        (CONTROL / "failed").write_text("浏览器异步夹具失败")
        raise


def coordinate_submission(engine):
    try:
        task_id = wait_file("submission")
        repository = TeachingRepository(engine)
        worker = SubmissionJobWorker(repository)
        token = str(uuid4())
        with repository.transaction() as connection:
            claimed = repository.claim_submission_job(
                connection, token, worker.LEASE_SECONDS
            )
        assert claimed is not None and claimed["id"] == task_id
        (CONTROL / "submission-running").write_text(task_id)
        assert wait_file("submission-complete") == task_id
        worker._complete(task_id, token)
        (CONTROL / "submission-succeeded").write_text(task_id)
    except Exception:
        (CONTROL / "submission-failed").write_text("浏览器正式提交夹具失败")
        raise


def main():
    settings = Settings.load(
        {**os.environ, "TEACHING_JOBS_ENABLED": "1"}, Path("app/BUILD_VERSION")
    )
    assert settings.mysql_database.startswith("campusclaw_test_")
    engine = mysql_engine(
        host=settings.mysql_host,
        port=settings.mysql_port,
        database=settings.mysql_database,
        user=settings.mysql_user,
        password=settings.mysql_password,
    )
    repository = TeachingJobs(engine)
    service = CandidateJobs(
        repository,
        DatabaseError,
        RetrievalRepository(engine),
        "synthetic-browser-v1",
        chat=Model(),
    )
    app = create_app(settings, candidate_jobs=service)
    threading.Thread(target=coordinate, args=(repository, service), daemon=True).start()
    threading.Thread(target=coordinate_submission, args=(engine,), daemon=True).start()
    app.run(host="0.0.0.0", port=8443, ssl_context="adhoc")


if __name__ == "__main__":
    main()
