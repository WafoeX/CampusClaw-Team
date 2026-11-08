"""Task 5.2：固定样本通过生产SSE宿主，模型/存储明确替身。"""

import json
from types import SimpleNamespace

import pytest

from scripts.evaluate_assistant import DATA, evaluate_case


@pytest.mark.parametrize(
    "case", json.loads(DATA.read_text())["cases"], ids=lambda case: case["id"]
)
def test_ST_N01_ST_F05_SK_F05_fixed_assistant_regression(case):
    assert evaluate_case(case)["passed"]


def test_ST_F04_evaluation_preserves_production_retry_and_cancel_contract():
    calls = []
    case = json.loads(DATA.read_text())["cases"][0]

    def complete(_messages, _deadline, **options):
        calls.append(options)
        return {
            "insufficient": False,
            "claims": [{"text": case["source"], "evidence": [1]}],
            "more": len(calls) == 1,
        }

    evaluate_case(case, SimpleNamespace(complete=complete))
    assert [call["allow_retry"] for call in calls] == [True, False]
    assert calls[0]["context"] is calls[1]["context"]
    assert calls[0]["context"].cancelled.is_set()
