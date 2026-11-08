"""2.0/ST-N01/ST-F04–07 传输前置，完整持久场景留后续组。"""

import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.services.access import AccessDenied
from app.services.answer_validation import validate_claims
from app.services.streaming import LongRequestCapacity, StreamContext, ValidatedStream


def decode(frames):
    return [
        json.loads(frame.split(b"data: ", 1)[1])
        for frame in frames
        if b"data: " in frame
    ]


def build(
    *, capacity=None, produce=None, validate=None, recheck=None, commit=None, **kwargs
):
    capacity = capacity or LongRequestCapacity()
    return ValidatedStream(
        capacity.reserve(),
        produce=produce or (lambda ctx: iter(["第一段", "第二段"])),
        validate=validate or (lambda value: value),
        recheck=recheck or (lambda: None),
        commit=commit or (lambda text: {"text": text}),
        metadata={"run_id": "synthetic"},
        request_id="request",
        validate_final=lambda raw, text: None,
        **kwargs,
    )


def test_ST_N01_segments_precede_commit_and_commit_precedes_done():
    committed = []
    stream = build(
        commit=lambda text: committed.append(text) or {"message_id": "synthetic"}
    )
    assert next(stream).startswith(b"event: meta\n")
    assert next(stream).startswith(b"event: delta\n") and not committed
    assert next(stream).startswith(b"event: delta\n") and not committed
    assert next(stream).startswith(b"event: done\n") and committed == ["第一段第二段"]
    assert list(stream) == []
    assert stream.reservation.capacity.active == 0


@pytest.mark.parametrize("invalid", ["", "\0", "\ud800", "a" * 12001])
def test_ST_F05_invalid_segment_never_enters_delta_or_commit(invalid):
    committed = []
    stream = build(produce=lambda ctx: iter([invalid]), commit=committed.append)
    frames = list(stream)
    assert [frame.split(b"\n")[0] for frame in frames] == [
        b"event: meta",
        b"event: error",
    ]
    assert decode(frames)[-1]["code"] == 1501 and not committed


def test_ST_F05_real_claim_validator_rejects_number_and_citation():
    evidence = [{"text": "电压为24伏"}]

    def validate(payload):
        text, _ = validate_claims(payload, evidence)
        return text

    for claim in (
        {"text": "电压为25伏", "evidence": [1]},
        {"text": "电压为24伏", "evidence": [2]},
    ):
        stream = build(
            produce=lambda ctx, claim=claim: iter(
                [{"insufficient": False, "claims": [claim]}]
            ),
            validate=validate,
        )
        frames = list(stream)
        assert not any(frame.startswith(b"event: delta") for frame in frames)
        assert decode(frames)[-1]["code"] == 1501


def test_ST_F04_upstream_failure_produces_one_safe_terminal_and_no_commit():
    def produce(ctx):
        yield "合法段落"
        raise OSError("synthetic-secret-must-not-escape")

    committed = []
    frames = list(build(produce=produce, commit=committed.append))
    assert [frame.split(b"\n")[0] for frame in frames] == [
        b"event: meta",
        b"event: delta",
        b"event: error",
    ]
    assert decode(frames)[-1]["code"] == 1500
    assert b"synthetic-secret" not in b"".join(frames) and not committed


def test_ST_F07_revocation_before_iteration_never_starts_upstream():
    calls = []

    def recheck():
        raise AccessDenied(401, 1100, "登录状态无效")

    stream = build(
        produce=lambda ctx: calls.append(1) or iter(["内容"]), recheck=recheck
    )
    frames = list(stream)
    assert len(frames) == 1 and decode(frames)[0]["code"] == 1100 and not calls
    assert stream.reservation.capacity.active == 0


def test_ST_F07_recheck_between_segments_prevents_further_text():
    revoked = False

    def recheck():
        if revoked:
            raise AccessDenied(409, 1400, "来源已变化")

    stream = build(recheck=recheck)
    next(stream)
    assert next(stream).startswith(b"event: delta")
    revoked = True
    remaining = list(stream)
    assert remaining[-1].startswith(b"event: error")
    assert decode(remaining)[-1]["code"] == 1400
    assert not any(frame.startswith(b"event: delta") for frame in remaining)


def test_ST_F06_unstarted_close_releases_once_without_source():
    calls = []
    stream = build(produce=lambda ctx: calls.append(1))
    stream.close()
    stream.close()
    assert not calls and stream.reservation.capacity.active == 0


def test_ST_F06_cancel_keeps_noncooperative_worker_charged_until_exit():
    blocked, release, exited = threading.Event(), threading.Event(), threading.Event()

    def produce(ctx):
        blocked.set()
        release.wait(timeout=2)
        try:
            ctx.check()
            yield "迟到内容"
        finally:
            exited.set()

    capacity = LongRequestCapacity(limit=1)
    stream = build(capacity=capacity, produce=produce)
    next(stream)
    assert blocked.wait(timeout=1)
    stream.close()
    assert capacity.active == 1
    with pytest.raises(AccessDenied) as rejected:
        capacity.reserve()
    assert rejected.value.code == 1600
    release.set()
    assert exited.wait(timeout=1)
    # worker在最后收尾时释放；用条件等待替代不受控睡眠。
    for _ in range(100):
        if capacity.active == 0:
            break
        threading.Event().wait(0.005)
    assert capacity.active == 0


def test_ST_F06_cancellation_callback_is_idempotent_even_registered_late():
    context = StreamContext(10)
    calls = []
    context.on_cancel(lambda: calls.append("first"))
    context.cancel()
    context.cancel()
    context.on_cancel(lambda: calls.append("late"))
    assert calls == ["first", "late"]


def test_ST_F04_timeout_aborts_without_success():
    clock = [0]
    stream = build(clock=lambda: clock[0])
    next(stream)
    clock[0] = 36
    frames = list(stream)
    assert decode(frames)[0]["code"] == 1500
    assert not any(frame.startswith(b"event: done") for frame in frames)


def test_ST_F07_draining_terminates_live_stream_and_rejects_admission():
    draining = [False]
    capacity = LongRequestCapacity(draining=lambda: draining[0])
    stream = build(capacity=capacity)
    next(stream)
    draining[0] = True
    frames = list(stream)
    assert decode(frames)[0]["code"] == 1500
    with pytest.raises(AccessDenied) as result:
        capacity.reserve()
    assert result.value.status == 503


def test_ST_B01_maximum_segments_and_output_budget():
    frames = list(build(produce=lambda ctx: iter(["a"] * 9)))
    assert sum(frame.startswith(b"event: delta") for frame in frames) == 8
    assert decode(frames)[-1]["code"] == 1501


def test_ST_B01_capacity_is_atomic_under_concurrent_admission():
    capacity = LongRequestCapacity()

    def acquire(_):
        try:
            return capacity.reserve()
        except AccessDenied as error:
            assert error.status == 429 and error.retry_after == 1
            return None

    with ThreadPoolExecutor(max_workers=10) as pool:
        reservations = [value for value in pool.map(acquire, range(10)) if value]
    assert len(reservations) == capacity.active == 4
    for reservation in reservations:
        reservation.release()
    assert capacity.active == 0


def test_ST_F06_commit_failure_never_sends_done():
    def commit(_text):
        raise OSError("synthetic storage failure")

    frames = list(build(commit=commit))
    assert decode(frames)[-1]["code"] == 1500
    assert not any(frame.startswith(b"event: done") for frame in frames)


def test_ST_F05_final_validation_precedes_commit():
    committed = []
    stream = build(commit=committed.append)

    def reject_final(raw, text):
        raise AccessDenied(502, 1501, "组合输出不合法")

    stream.validate_final = reject_final
    frames = list(stream)
    assert decode(frames)[-1]["code"] == 1501 and not committed


def test_ST_F04_failed_worker_start_does_not_leak_slot(monkeypatch):
    stream = build()

    def fail(_thread):
        raise RuntimeError("synthetic resource exhaustion")

    monkeypatch.setattr(threading.Thread, "start", fail)
    frames = list(stream)
    assert decode(frames)[-1]["code"] == 1500
    assert stream.reservation.capacity.active == 0
