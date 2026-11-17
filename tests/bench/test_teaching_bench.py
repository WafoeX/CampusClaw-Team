"""显式执行的隔离压测，复用真实 Compose 夹具。"""

import os
from pathlib import Path

from tests.integration.test_compose import eventually
from tests.integration.test_compose import stack as stack


def test_L10_N06_teaching_benchmark(stack):
    compose, _, status, _ = stack
    status("ready")
    compose("up", "-d", "kafka-topics", teaching=True)
    eventually(
        lambda: (
            compose("logs", "--no-log-prefix", "kafka-topics", teaching=True).count(
                "Created topic"
            )
            == 2
        )
    )
    settings = [
        item
        for name in ("LEVELS", "SAMPLES", "QUIZZES")
        if (value := os.getenv(f"CAMPUSCLAW_BENCH_{name}")) is not None
        for item in ("-e", f"CAMPUSCLAW_BENCH_{name}={value}")
    ]
    output = compose(
        "exec",
        "-T",
        *settings,
        "app",
        "python",
        "-c",
        Path(__file__).with_name("teaching_bench.py").read_text(),
    )
    assert "teaching_benchmark " in output
    print(output)
