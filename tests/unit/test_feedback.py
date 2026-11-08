"""FB-F01/B02：评价白名单、Unicode长度与修订值。"""

import pytest

from app.services.access import AccessDenied
from app.services.feedback import feedback_input


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"rating": "other", "expected_revision": 0},
        {"rating": "unresolved", "note": " ", "expected_revision": 0},
        {"rating": "helpful", "note": "字" * 501, "expected_revision": 0},
        {"rating": "helpful", "expected_revision": True},
        {"rating": "helpful", "expected_revision": -1},
        {"rating": "helpful", "expected_revision": 0, "class_id": "b"},
        {"rating": "helpful", "note": "\ud800", "expected_revision": 0},
    ],
)
def test_FB_F01_invalid_feedback(payload):
    with pytest.raises(AccessDenied) as error:
        feedback_input(payload)
    assert error.value.status == 400 and error.value.code == 1000


def test_FB_B02_normalized_note_and_optional_helpful_note():
    assert feedback_input(
        {"rating": "unresolved", "note": " 卡点🙂 ", "expected_revision": 0}
    ) == ("unresolved", "卡点🙂", 0)
    assert feedback_input({"rating": "helpful", "expected_revision": 3}) == (
        "helpful",
        None,
        3,
    )
    assert (
        len(
            feedback_input(
                {"rating": "unresolved", "note": "🙂" * 500, "expected_revision": 0}
            )[1]
        )
        == 500
    )
