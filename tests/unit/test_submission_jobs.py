from contextlib import nullcontext
from datetime import datetime
from unittest.mock import Mock

import pytest

from app.services.submission_jobs import SubmissionInvariantError, SubmissionJobWorker
from app.submission_worker import worker_ready

NOW = datetime(2030, 1, 1)


def repository(job=None, *, prior=None):
    value = Mock()
    value.transaction.side_effect = lambda: nullcontext(Mock())
    value.claim_submission_job.return_value = job
    value.locked_submission_job.return_value = job
    value.quiz.return_value = {
        "published_at": NOW,
        "deadline_at": datetime(2030, 1, 2),
    }
    value.participant.return_value = {"student_id": "student"}
    value.items.return_value = [
        {"id": "item-a", "answer": "A", "points": 10},
        {"id": "item-b", "answer": "B", "points": 5},
    ]
    value.submission.return_value = prior
    value.now.return_value = NOW
    value.finish_submission_job.return_value = 1
    return value


def job(**changes):
    return {
        "id": "task",
        "submission_id": "submission",
        "class_id": "class",
        "quiz_id": "quiz",
        "student_id": "student",
        "request_key": b"key",
        "fingerprint": b"fingerprint",
        "answers": {"item-a": "A", "item-b": "A"},
        "accepted_at": NOW,
        **changes,
    }


def test_ASJ_N01_worker_scores_once_and_clears_task_payload():
    store = repository(job())
    worker = SubmissionJobWorker(store)

    assert worker.run_once() is True
    submission, result, created = store.submit.call_args.args[1:]
    assert submission["id"] == "submission" and created == NOW
    assert result["score"] == 10 and result["max_score"] == 15
    assert result["details"] == [
        {"item_id": "item-a", "correct": True, "awarded_points": 10},
        {"item_id": "item-b", "correct": False, "awarded_points": 0},
    ]
    assert store.finish_submission_job.call_count == 1


def test_ASJ_B01_recovered_existing_submission_is_not_scored_twice():
    current = job()
    store = repository(
        current,
        prior={"id": "submission", "fingerprint": b"fingerprint"},
    )
    assert SubmissionJobWorker(store).run_once() is True
    store.submit.assert_not_called()
    store.finish_submission_job.assert_called_once()


@pytest.mark.parametrize(
    "change,repository_change",
    [
        ({"accepted_at": datetime(2030, 1, 3)}, {}),
        ({"answers": {"unknown": "A"}}, {}),
        ({}, {"participant": None}),
        ({}, {"quiz": None}),
    ],
)
def test_ASJ_F05_resource_changes_fail_without_submission(change, repository_change):
    current = job(**change)
    store = repository(current)
    for name, value in repository_change.items():
        getattr(store, name).return_value = value

    assert SubmissionJobWorker(store).run_once() is True
    store.submit.assert_not_called()
    store.fail_submission_job.assert_called_once()


def test_ASJ_B02_no_due_job_does_not_open_processing_transaction():
    store = repository(None)
    assert SubmissionJobWorker(store).run_once() is False
    assert store.transaction.call_count == 1


def test_ASJ_F05_lost_lease_cannot_claim_success():
    store = repository(job())
    store.finish_submission_job.return_value = 0
    worker = SubmissionJobWorker(store)
    with pytest.raises(SubmissionInvariantError):
        worker._complete("task", "old-token")


def test_worker_readiness_requires_database_connection():
    connection = Mock()
    engine = Mock()
    engine.connect.return_value = nullcontext(connection)

    worker_ready(engine)

    statement = connection.execute.call_args.args[0]
    assert str(statement) == "SELECT 1"
