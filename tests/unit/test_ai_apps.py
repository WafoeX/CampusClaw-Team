"""AP-N01/B01/F01/F04：模板变量和固定模型输入/输出契约。"""

import json

import pytest

from app.services.access import AccessDenied
from app.services.ai_contracts import (
    APP_POLICIES,
    configuration_input,
    prompt_text,
    render_prompt,
    run_messages,
    validate_output,
    variables,
)


@pytest.mark.parametrize(
    "prompt",
    [
        "{{unknown}}",
        "{{input.name}}",
        "{{input[0]}}",
        "{{{{input}}}}",
        "{%for x%}",
        "a" * 2001,
    ],
)
def test_AP_F01_rejects_expressions_and_prompt_boundaries(prompt):
    with pytest.raises(AccessDenied) as result:
        prompt_text(prompt)
    assert result.value.code == 1000


def test_AP_N01_preview_and_execution_use_single_pass_substitution():
    values = variables({"input": "  {{audience}}原文  ", "audience": "同学"})
    prompt = prompt_text("润色{{input}}，读者{{audience}}")
    expected = "润色{{audience}}原文，读者同学"
    assert render_prompt(prompt, values) == expected
    for app in APP_POLICIES:
        messages = run_messages(app, prompt, values)
        assert json.loads(messages[1]["content"])["rendered_prompt"] == expected
        assert "{{audience}}原文" not in messages[0]["content"]
        assert "tools" not in json.loads(messages[1]["content"])


@pytest.mark.parametrize(
    "values",
    [
        {"input": ""},
        {"input": "x" * 4001},
        {"input": "x", "role": "teacher"},
        {"input": False},
        {"input": "x", "audience": "a" * 121},
    ],
)
def test_AP_F01_invalid_variables_fail_before_model(values):
    with pytest.raises(AccessDenied):
        variables(values)


def test_AP_F01_render_budget_cannot_be_amplified_by_repeated_variables():
    with pytest.raises(AccessDenied):
        render_prompt("{{input}}" * 4, variables({"input": "x" * 4000}))


def test_AP_B01_empty_prompt_and_exact_false_enabled_are_valid():
    payload = {
        "name": "助手",
        "prompt": " ",
        "enabled": False,
        "material_ids": [],
        "skill_ids": [],
    }
    assert configuration_input("assistant", payload)["prompt"] == ""
    assert configuration_input("assistant", payload)["enabled"] is False


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"text": ""},
        {"text": "bad", "tool_calls": []},
        {"text": "\ud800"},
        {"text": "a" * 12001},
        {"text": False},
    ],
)
def test_AP_F04_invalid_model_output_is_not_a_success(payload):
    with pytest.raises(AccessDenied) as result:
        validate_output(payload)
    assert result.value.status == 502 and result.value.code == 1501


def test_AP_N01_ten_valid_and_ten_invalid_fixed_outputs():
    valid = [{"text": f"合成学习建议 {index}"} for index in range(10)]
    invalid = [{"text": "被拒", "unexpected": index} for index in range(10)]
    assert [validate_output(item) for item in valid] == [item["text"] for item in valid]
    for item in invalid:
        with pytest.raises(AccessDenied):
            validate_output(item)


@pytest.mark.parametrize(
    "value", ["2026-12-01", "not-a-date", "2026-12-01T00:00:00+08:00"]
)
def test_AP_F04_private_expiry_requires_explicit_utc(config_env, tmp_path, value):
    from app.config import ConfigError, Settings

    version_file = tmp_path / "version"
    version_file.write_text("test-build")
    with pytest.raises(ConfigError, match="AI_DATA_EXPIRES_AT"):
        Settings.load(config_env | {"AI_DATA_EXPIRES_AT": value}, version_file)
