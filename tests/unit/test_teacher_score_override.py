"""TSO：教师覆盖分的授权、修订、重放和事务失败。"""

from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.services.access import AccessDenied
from app.services.teaching import TeachingService

IDENTITY = SimpleNamespace(class_id="class-a", subject_id="teacher-a")
NOW = datetime(2030, 1, 1)
COOKIE = "a" * 43


def service(row):
    connection = object()
    repository = Mock()

    @contextmanager
    def transaction():
        yield connection

    repository.transaction = transaction
    repository.lock_actor.return_value = SimpleNamespace(
        class_id="class-a", role="teacher"
    )
    repository.quiz.return_value = {"id": "quiz-a"}
    repository.score_submission.return_value = row
    repository.now.return_value = NOW
    return TeachingService(repository, RuntimeError), repository


def score_row(**overrides):
    return {
        "id": "submission-a",
        "rule_score": 6,
        "max_score": 10,
        "override_score": None,
        "override_reason": None,
        "override_revision": None,
    } | overrides


def test_TSO_N01_first_override_preserves_rule_score_and_appends_event():
    target, repository = service(score_row())
    result = target.override_score(
        IDENTITY, COOKIE, "quiz-a", "submission-a", 0, 8, "复核步骤正确"
    )
    assert result == {
        "submission_id": "submission-a",
        "rule_score": 6,
        "score": 8,
        "score_source": "teacher_override",
        "reason": "复核步骤正确",
        "revision": 1,
    }
    assert repository.save_score_override.call_args.kwargs == {
        "submission_id": "submission-a",
        "class_id": "class-a",
        "teacher_id": "teacher-a",
        "previous_score": 6,
        "score": 8,
        "reason": "复核步骤正确",
        "revision": 1,
        "now": NOW,
    }


def test_TSO_N01_identical_replay_does_not_write_again():
    target, repository = service(
        score_row(
            override_score=8,
            override_reason="复核步骤正确",
            override_revision=1,
        )
    )
    result = target.override_score(
        IDENTITY, COOKIE, "quiz-a", "submission-a", 0, 8, "复核步骤正确"
    )
    assert result["revision"] == 1
    repository.save_score_override.assert_not_called()


@pytest.mark.parametrize(
    ("row", "revision", "score", "status", "code"),
    [
        (score_row(), 1, 8, 409, 1400),
        (score_row(), 0, 11, 400, 1000),
        (None, 0, 8, 404, 1300),
    ],
)
def test_TSO_F01_F03_invalid_revision_range_or_missing_has_no_write(
    row, revision, score, status, code
):
    target, repository = service(row)
    with pytest.raises(AccessDenied) as raised:
        target.override_score(
            IDENTITY,
            COOKIE,
            "quiz-a",
            "submission-a",
            revision,
            score,
            "合成理由",
        )
    assert (raised.value.status, raised.value.code) == (status, code)
    repository.save_score_override.assert_not_called()


def test_TSO_F04_storage_failure_is_mapped_to_dependency_error():
    target, repository = service(score_row())
    repository.save_score_override.side_effect = RuntimeError("synthetic")
    with pytest.raises(AccessDenied) as raised:
        target.override_score(
            IDENTITY, COOKIE, "quiz-a", "submission-a", 0, 8, "合成理由"
        )
    assert (raised.value.status, raised.value.code) == (503, 1500)
