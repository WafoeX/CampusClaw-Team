"""QA-N01/B01/F05：固定10条可答、10条应拒绝的确定性输出边界。"""

import pytest

from app.services.access import AccessDenied
from app.services.answer_validation import assemble_evidence, validate_claims

POSITIVE = [
    ("星海灯塔每周五检修。", "星海灯塔每周五检修。"),
    ("额定电压为24伏。", "额定电压为24V。"),
    ("额定电压为24000毫伏。", "额定电压为24伏。"),
    ("合格率为20%。", "合格率为0.2。"),
    ("合格率为0.2。", "合格率为20%。"),
    ("额定电压为24伏。", "额定电压为二十四伏。"),
    ("反应温度为72摄氏度。", "反应温度为72℃。"),
    ("处理时长为2分钟。", "处理时长为120秒。"),
    ("参加人数为二十人。", "参加人数为20人。"),
    ("线路长度为100厘米。", "线路长度为1米。"),
]


@pytest.mark.parametrize(("source", "text"), POSITIVE)
def test_QA_N01_fixed_ten_supported_outputs(source, text):
    answer, ids = validate_claims(
        {"insufficient": False, "claims": [{"text": text, "evidence": [1]}]},
        [{"text": source}],
    )
    assert answer == text and ids == [1]


NEGATIVE = [
    {"text": "额定电压为25伏。", "evidence": [1]},
    {"text": "额定电压为24安。", "evidence": [1]},
    {"text": "额定电压为24伏。", "evidence": [9]},
    {"text": "额定电压为24伏。", "evidence": []},
    {"text": False, "evidence": [1]},
    {"text": "额定电压为24伏。", "evidence": [1], "class_id": "other"},
    {"text": "额定电压为24+5=29伏。", "evidence": [1]},
    {"text": "电流为24安。", "evidence": [1]},
    {"text": "额定电压为24伏。", "evidence": [True]},
    {"text": "电压为24miles。", "evidence": [1]},
]


@pytest.mark.parametrize("claim", NEGATIVE)
def test_QA_F05_fixed_ten_invalid_outputs_are_rejected(claim):
    with pytest.raises(AccessDenied) as error:
        validate_claims(
            {"insufficient": False, "claims": [claim]},
            [{"text": "额定电压为24伏，电流为5安。"}],
        )
    assert error.value.status == 502 and error.value.code == 1501


def test_QA_B01_evidence_budget_uses_complete_prefix_and_contiguous_mapping():
    assert len(assemble_evidence([{"text": "字" * 1500} for _ in range(9)])) == 8
    assert len(assemble_evidence([{"text": "字" * 1501} for _ in range(8)])) == 7
    assert assemble_evidence([{"text": "字" * 12001}]) == []


def test_QA_B01_model_insufficient_has_empty_claims_only():
    assert validate_claims(
        {"insufficient": True, "claims": []}, [{"text": "资料"}]
    ) == (None, [])
    with pytest.raises(AccessDenied):
        validate_claims(
            {"insufficient": True, "claims": [{"text": "资料", "evidence": [1]}]},
            [{"text": "资料"}],
        )
