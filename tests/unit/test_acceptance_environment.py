"""预验收编排的凭据保留、目标隔离和网关端口边界。"""

import json
import stat

import pytest

from scripts.dependency_sources import mirrored_dependencies
from scripts.start_acceptance import (
    configuration,
    gateway_service,
    model_values,
    private_json,
)


def test_configuration_is_per_clone_preserves_database_secrets_and_refreshes_models(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("os.getuid", lambda: 1000)
    project, initial = configuration(
        tmp_path, {}, {"CHAT_API_KEY": "fixture-only"}, "a" * 40
    )
    other_project, other = configuration(tmp_path / "another", {}, {}, "a" * 40)
    assert (
        project != other_project
        and initial["MYSQL_DATABASE"] != other["MYSQL_DATABASE"]
    )
    _, again = configuration(tmp_path, initial, {}, "b" * 40)
    for key in (
        "MYSQL_PASSWORD",
        "MYSQL_ROOT_PASSWORD",
        "CAMPUSCLAW_SEED_PASSWORD",
        "MCP_SERVICE_TOKEN",
    ):
        assert again[key] == initial[key]
    assert "CHAT_API_KEY" not in again and again["APP_BUILD_REVISION"] == "b" * 40
    assert again["APP_PUBLIC_ORIGIN"] == "https://localhost:8444"
    assert again["TEACHING_JOBS_ENABLED"] == "1"
    assert again["APP_HOST_PORT"] == "18000"


def test_configuration_cannot_redirect_database_or_use_root(tmp_path, monkeypatch):
    monkeypatch.setattr("os.getuid", lambda: 1000)
    with pytest.raises(ValueError, match="专用合成库"):
        configuration(tmp_path, {"MYSQL_DATABASE": "shared"}, {}, "a" * 40)
    monkeypatch.setattr("os.getuid", lambda: 0)
    with pytest.raises(ValueError, match="非 root"):
        configuration(tmp_path, {}, {}, "a" * 40)


def test_private_configuration_modes_and_model_input_are_not_executed(tmp_path):
    target = tmp_path / "config.json"
    target.write_text("{}")
    target.chmod(0o666)
    private_json(target, {"secret": "synthetic-value"})
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert json.loads(target.read_text()) == {"secret": "synthetic-value"}
    env = tmp_path / ".env"
    env.write_text(
        "IGNORED=other\nCHAT_MODEL='course-chat'\nCHAT_API_KEY='literal$(not-a-command)'\n"
    )
    assert model_values(env) == {
        "CHAT_MODEL": "course-chat",
        "CHAT_API_KEY": "literal$(not-a-command)",
    }
    env.write_text('CHAT_API_KEY="broken')
    with pytest.raises(ValueError, match="CHAT_API_KEY"):
        model_values(env)


def test_gateway_override_has_only_loopback_acceptance_port_and_preserves_hardening(
    tmp_path,
):
    original = {
        "image": "fixture@sha256:" + "a" * 64,
        "ports": ["127.0.0.1:8443:8443"],
        "read_only": True,
        "cap_drop": ["ALL"],
        "volumes": [
            {"source": "/old", "target": "/etc/campusclaw/tls", "read_only": True}
        ],
    }
    gateway = gateway_service(original, tmp_path)
    assert gateway["ports"] == ["127.0.0.1:8444:8443"]
    assert gateway["read_only"] and gateway["cap_drop"] == ["ALL"]
    assert gateway["volumes"][0]["source"] == str(tmp_path)
    assert original["volumes"][0]["source"] == "/old"


def test_gateway_and_queue_sources_keep_all_pinned_digests():
    config = {
        "services": {
            "gateway": {"image": "nginx:fixture@sha256:" + "a" * 64},
            "kafka": {"image": "apache/kafka:fixture@sha256:" + "b" * 64},
            "kafka-topics": {"image": "apache/kafka:fixture@sha256:" + "b" * 64},
        }
    }
    override = mirrored_dependencies(
        config, "mirror.example", ("gateway", "kafka", "kafka-topics")
    )
    for service in override["services"]:
        assert (
            override["services"][service]["image"].split("@", 1)[1]
            == config["services"][service]["image"].split("@", 1)[1]
        )
