"""L10-04：制品作业只对依赖镜像限流重试，并保留最终失败。"""

import io
import json
import subprocess
import tarfile
from unittest.mock import Mock, call

import pytest

from scripts import build_candidate
from scripts.verify_runtime import VerificationError


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


def image_archive(path, layers):
    with tarfile.open(path, "w") as image:
        manifest = []
        for ordinal, paths in enumerate(layers):
            content = io.BytesIO()
            with tarfile.open(fileobj=content, mode="w:gz") as layer:
                for name in paths:
                    layer.addfile(tarfile.TarInfo(name))
            data = content.getvalue()
            member = tarfile.TarInfo(f"layer-{ordinal}.tar.gz")
            member.size = len(data)
            image.addfile(member, io.BytesIO(data))
            manifest.append(member.name)
        data = json.dumps([{"Layers": manifest}]).encode()
        member = tarfile.TarInfo("manifest.json")
        member.size = len(data)
        image.addfile(member, io.BytesIO(data))


def test_L10_N04_runtime_layers_preserve_bytecode_and_templates(tmp_path):
    image = tmp_path / "app.tar"
    entrypoint = "srv/campusclaw/app/__main__.pyc"
    image_archive(
        image,
        [
            ["usr/local/lib/python3.13/pathlib.py"],
            [entrypoint, "srv/campusclaw/app/templates/login.html"],
        ],
    )
    assert build_candidate.inspect_runtime_layers(image, entrypoint) == 2


@pytest.mark.parametrize(
    "forbidden",
    [
        "srv/campusclaw/app/__main__.py",
        "usr/local/bin/uv",
        "usr/local/lib/python3.13/ensurepip/__init__.py",
    ],
)
def test_L10_N04_runtime_layers_reject_files_hidden_by_whiteout(tmp_path, forbidden):
    image = tmp_path / "app.tar"
    entrypoint = "srv/campusclaw/app/__main__.pyc"
    folder, filename = forbidden.rsplit("/", 1)
    image_archive(image, [[forbidden], [f"{folder}/.wh.{filename}", entrypoint]])
    with pytest.raises(VerificationError, match="镜像层含有不应交付的文件"):
        build_candidate.inspect_runtime_layers(image, entrypoint)
