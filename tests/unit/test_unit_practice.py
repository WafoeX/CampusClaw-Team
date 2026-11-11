import pytest

from app.services.access import AccessDenied, Identity
from app.services.sessions import request_input
from app.services.unit_practice import TTL_SECONDS, UnitPractice


def test_TD_N02_TD_F07_practice_bound_to_authoritative_identity_and_turn():
    now = [100]
    practice = UnitPractice(b"synthetic fixture signing key", lambda: now[0])
    identity = Identity("actor-a", "class-a", frozenset())
    issued = practice.issue(identity, "session-a", b"turn")
    token = issued["practice_context"]
    context = practice.verify(identity, "session-a", b"turn", issued["question"], token)
    assert practice.question(context["arguments"]) == issued["question"]
    practice.check_expiry(context)
    for actor, session, key, question, supplied in (
        (identity, "session-a", b"turn", "修改题面", token),
        (identity, "session-a", b"another", issued["question"], token),
        (identity, "session-b", b"turn", issued["question"], token),
        (
            Identity("other-a", "class-a", frozenset()),
            "session-a",
            b"turn",
            issued["question"],
            token,
        ),
        (
            Identity("actor-a", "class-b", frozenset()),
            "session-a",
            b"turn",
            issued["question"],
            token,
        ),
        (identity, "session-a", b"turn", issued["question"], "x" + token),
    ):
        with pytest.raises(AccessDenied) as failure:
            practice.verify(actor, session, key, question, supplied)
        assert failure.value.code == 1000
    now[0] += TTL_SECONDS
    with pytest.raises(AccessDenied, match="过期"):
        practice.check_expiry(context)


def test_TD_B01_selection_keeps_legacy_fingerprint_and_canonical_order():
    assert request_input({"question": "单位练习"}) == request_input(
        {"question": "单位练习", "selected_tools": []}
    )
    assert request_input(
        {"question": "单位练习", "selected_tools": ["unit_convert@a", "formula_hint@a"]}
    )["selected_tools"] == ["formula_hint@a", "unit_convert@a"]
    with pytest.raises(AccessDenied):
        request_input(
            {"question": "单位练习", "selected_tools": ["formula_hint@a"] * 2}
        )
