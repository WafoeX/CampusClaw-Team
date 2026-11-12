"""LI-01：冻结名单与已评分正式提交的统计口径。"""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from app.services.access import AccessDenied
from app.services.teaching import TeachingService


def candidate(participants, rows, chapter="chapter-a"):
    repository = MagicMock()
    repository.quiz.return_value = {
        "id": "quiz-a",
        "class_id": "class-a",
        "published_at": datetime(2030, 1, 1),
        "chapter_id": chapter,
    }
    repository.items.return_value = [
        {"id": "item-a", "position": 1},
        {"id": "item-b", "position": 2},
    ]
    repository.insight_rows.return_value = participants, rows
    repository.unresolved_count.return_value = 3
    repository.now.return_value = datetime(2030, 1, 2, tzinfo=UTC)
    identity = SimpleNamespace(class_id="class-a", subject_id="teacher-a")
    return TeachingService(repository, RuntimeError), identity


def test_LI_N01_frozen_participants_scored_results_and_item_denominator():
    service, identity = candidate(
        4,
        [
            {"score": 60, "details": [{"item_id": "item-a", "correct": True}]},
            {"score": 100, "details": [{"item_id": "item-a", "correct": False}]},
        ],
    )
    view = service.insights(identity, "quiz-a")
    assert view["submission_rate"] == 50
    assert view["average_score"] == 80
    assert view["item_accuracy"][0]["correct_rate"] == 50
    assert view["item_accuracy"][1]["correct_rate"] == 0
    assert view["unresolved_count"] == 3


def test_LI_B01_zero_scored_denominator_is_no_data():
    service, identity = candidate(4, [])
    view = service.insights(identity, "quiz-a")
    assert view["submission_rate"] == 0
    assert view["average_score"] is None
    assert all(item["correct_rate"] is None for item in view["item_accuracy"])


def test_LI_F02_mistakes_hidden_until_answer_open():
    service, identity = candidate(1, [])
    service.my_submission = Mock(return_value={"submitted": True, "answers": {}})
    assert service.my_mistakes(identity, "quiz-a") == {"open": False, "items": []}
    service.repository.items.assert_not_called()


def test_LI_N01_open_mistakes_include_only_wrong_or_unanswered_items():
    service, identity = candidate(1, [])
    service.my_submission = Mock(
        return_value={
            "submitted": True,
            "answers": {"item-a": "B"},
            "details": [
                {
                    "item_id": "item-a",
                    "correct": False,
                    "answer": "A",
                    "explanation": "解析",
                },
                {"item_id": "item-b", "correct": True},
            ],
        }
    )
    service.repository.items.return_value = [
        {
            "id": "item-a",
            "stem": "题干",
            "options": ["甲", "乙"],
            "source_material_id": None,
        },
        {
            "id": "item-b",
            "stem": "其他",
            "options": ["甲", "乙"],
            "source_material_id": None,
        },
    ]
    view = service.my_mistakes(identity, "quiz-a")
    assert view["open"] is True
    assert len(view["items"]) == 1
    assert view["items"][0]["item_id"] == "item-a"
    assert view["items"][0]["source_status"] == "unavailable"


def test_LI_F03_missing_quiz_is_hidden():
    service, identity = candidate(1, [])
    service.repository.quiz.return_value = None
    with pytest.raises(AccessDenied) as error:
        service.insights(identity, "missing")
    assert error.value.status == 404 and error.value.code == 1300


def test_LI_F04_repository_failure_is_dependency_error():
    service, identity = candidate(1, [])
    service.repository.insight_rows.side_effect = RuntimeError("database unavailable")
    with pytest.raises(AccessDenied) as error:
        service.insights(identity, "quiz-a")
    assert error.value.status == 503 and error.value.code == 1500
