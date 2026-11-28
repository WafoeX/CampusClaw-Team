"""正式交卷任务的确定性评分与租约恢复。"""

from uuid import NAMESPACE_URL, uuid4, uuid5

from app.services.access import Identity
from app.services.operation_audit import append_audit


class SubmissionInvariantError(Exception):
    pass


class SubmissionJobWorker:
    LEASE_SECONDS = 30

    def __init__(self, repository):
        self.repository = repository

    def run_once(self):
        token = str(uuid4())
        with self.repository.transaction() as connection:
            claim = self.repository.claim_submission_job(
                connection, token, self.LEASE_SECONDS
            )
        if claim is None:
            return False
        try:
            self._complete(claim["id"], token)
        except SubmissionInvariantError:
            self._fail(claim["id"], token, "resource_changed")
        return True

    @staticmethod
    def _duration(job, now):
        return max(0, round((now - job["accepted_at"]).total_seconds() * 1000))

    def _audit(self, connection, job, now, outcome):
        append_audit(
            self.repository,
            connection,
            Identity(job["student_id"], job["class_id"], frozenset()),
            now,
            uuid5(
                NAMESPACE_URL,
                f"submission-job:{job['id']}:terminal:{outcome}",
            ).hex,
            "submission_terminal",
            "submission_job",
            resource_id=job["id"],
            outcome=outcome,
            duration_ms=self._duration(job, now),
        )

    def _fail(self, task_id, token, code):
        with self.repository.transaction() as connection:
            job = self.repository.locked_submission_job(connection, task_id, token)
            if job is None:
                return
            now = self.repository.now(connection)
            if not self.repository.fail_submission_job(
                connection, task_id, token, code, now
            ):
                raise SubmissionInvariantError()
            self._audit(connection, job, now, "failed")

    def _complete(self, task_id, token):
        with self.repository.transaction() as connection:
            job = self.repository.locked_submission_job(connection, task_id, token)
            if job is None:
                return
            quiz = self.repository.quiz(
                connection, job["class_id"], job["quiz_id"], lock=True
            )
            participant = self.repository.participant(
                connection,
                job["class_id"],
                job["quiz_id"],
                job["student_id"],
                lock=True,
            )
            items = self.repository.items(connection, job["class_id"], job["quiz_id"])
            if (
                quiz is None
                or quiz["published_at"] is None
                or participant is None
                or job["accepted_at"] >= quiz["deadline_at"]
                or job["answers"] is None
                or not items
                or set(job["answers"]) - {item["id"] for item in items}
            ):
                raise SubmissionInvariantError()
            prior = self.repository.submission(
                connection, job["class_id"], job["quiz_id"], job["student_id"]
            )
            if prior is not None:
                if (
                    prior["id"] != job["submission_id"]
                    or prior["fingerprint"] != job["fingerprint"]
                ):
                    raise SubmissionInvariantError()
            else:
                details = [
                    {
                        "item_id": item["id"],
                        "correct": job["answers"].get(item["id"]) == item["answer"],
                        "awarded_points": item["points"]
                        if job["answers"].get(item["id"]) == item["answer"]
                        else 0,
                    }
                    for item in items
                ]
                submission = {
                    "id": job["submission_id"],
                    "quiz_id": job["quiz_id"],
                    "class_id": job["class_id"],
                    "student_id": job["student_id"],
                    "request_key": job["request_key"],
                    "fingerprint": job["fingerprint"],
                    "answers": job["answers"],
                    "accepted_at": job["accepted_at"],
                }
                result = {
                    "submission_id": job["submission_id"],
                    "score": sum(row["awarded_points"] for row in details),
                    "max_score": sum(item["points"] for item in items),
                    "details": details,
                    "scoring_version": 1,
                    "created_at": self.repository.now(connection),
                }
                self.repository.submit(
                    connection, submission, result, result["created_at"]
                )
            now = self.repository.now(connection)
            if not self.repository.finish_submission_job(
                connection, task_id, token, now
            ):
                raise SubmissionInvariantError()
            self._audit(connection, job, now, "succeeded")
