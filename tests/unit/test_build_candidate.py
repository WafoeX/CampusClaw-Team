"""L10-04：制品作业只对依赖镜像限流重试，并保留最终失败。"""

import subprocess
from unittest.mock import Mock, call

import pytest

from scripts import build_candidate


def test_L10_04_dependency_pull_recovers_after_rate_limit(monkeypatch):
    denied = subprocess.CalledProcessError(
        1, "compose pull", stderr="toomanyrequests: Rate exceeded\n"
    )
    compose = Mock(side_effect=[denied, ""])
    sleep = Mock()
    monkeypatch.setattr(build_candidate.time, "sleep", sleep)

    build_candidate.pull_dependency(compose, "mysql")

    pull = call(
        "pull", "--policy", "missing", "mysql", stderr=subprocess.PIPE, timeout=180
    )
    assert compose.call_args_list == [pull, pull]
    sleep.assert_called_once_with(10)


@pytest.mark.parametrize(
    ("message", "delays"),
    [("toomanyrequests: Rate exceeded\n", [10, 30]), ("manifest unknown\n", [])],
)
def test_L10_04_dependency_pull_stays_failed(message, delays, monkeypatch, capsys):
    denied = subprocess.CalledProcessError(1, "compose pull", stderr=message)
    compose = Mock(side_effect=denied)
    sleep = Mock()
    monkeypatch.setattr(build_candidate.time, "sleep", sleep)

    with pytest.raises(subprocess.CalledProcessError) as raised:
        build_candidate.pull_dependency(compose, "qdrant")

    assert raised.value is denied
    assert compose.call_count == len(delays) + 1
    assert sleep.call_args_list == [call(delay) for delay in delays]
    assert message in capsys.readouterr().err
