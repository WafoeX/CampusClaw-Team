"""ST-F01：问题、范围与幂等键边界；完整并发与原子性另做真实MySQL。"""

import pytest

from app.services.access import AccessDenied
from app.services.sessions import request_input, valid_key


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"question": " "},
        {"question": "字"},
        {"question": "问" * 501},
        {"question": True},
        {"question": "问题", "class_id": "b"},
        {"question": "问题", "chapter_scope": None},
        {"question": "问题", "retrieval_mode": []},
        {"question": "\ud800x"},
        {"question": "问\0题"},
    ],
)
def test_ST_F01_invalid_input(payload):
    with pytest.raises(AccessDenied) as error:
        request_input(payload)
    assert error.value.code == 1000


def test_ST_B01_current_question_is_normalized_without_history():
    assert request_input({"question": "  当前问题  "}) == {
        "question": "当前问题",
        "chapter_scope": None,
        "retrieval_mode": "keyword",
    }
    assert len(request_input({"question": "问" * 500})["question"]) == 500


@pytest.mark.parametrize("value", [b"", b"x" * 65, b"a.b", b"\xff", "abc", None])
def test_ST_F01_invalid_key(value):
    with pytest.raises(AccessDenied):
        valid_key(value)
