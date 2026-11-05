import json

import pytest

from scripts.scenario_trace import check_traceability


@pytest.fixture
def trace(tmp_path):
    spec = tmp_path / "openspec/changes/fixture/specs/auth/spec.md"
    spec.parent.mkdir(parents=True)
    spec.write_text("#### Scenario: AUTH-N01 正常\n")
    test = tmp_path / "tests/test_auth.py"
    test.parent.mkdir()
    test.write_text("def test_auth():\n    assert True\n")
    manifest = {
        "version": 1,
        "implemented": {
            "fixture/specs/auth/spec.md": {
                "AUTH-N01": {"test": "tests/test_auth.py", "function": "test_auth"}
            }
        },
        "planned": {},
    }
    return tmp_path, spec, test, manifest


def check(trace):
    root, _, _, manifest = trace
    (root / "tests/scenario-map.json").write_text(json.dumps(manifest))
    return check_traceability(root)


def test_TR_N01_TR_B01_real_entry_and_archive(trace):
    root, spec, _, _ = trace
    assert check(trace) == []
    archived = root / "openspec/changes/archive/2030-fixture"
    archived.parent.mkdir()
    spec.parents[2].rename(archived)
    assert check(trace) == []


def test_TR_F01_new_business_scenario_without_test_fails(trace):
    _, spec, _, _ = trace
    spec.write_text(spec.read_text() + "#### Scenario: AUTH-F99 新增失败\n")
    assert any("AUTH-F99" in error for error in check(trace))


@pytest.mark.parametrize("defect", ("file", "function", "assertion"))
def test_TR_F02_missing_executable_evidence_fails(trace, defect):
    _, _, test, _ = trace
    if defect == "file":
        test.unlink()
    elif defect == "function":
        test.write_text("def renamed():\n    assert True\n")
    else:
        test.write_text("def test_auth():\n    pass\n")
    assert any("无效场景映射" in error for error in check(trace))


@pytest.mark.parametrize(
    "content", ("{", '{"version":1,"version":1}', '{"version":1}', "[]")
)
def test_TR_F03_invalid_or_duplicate_manifest_fails(trace, content):
    root, _, _, _ = trace
    (root / "tests/scenario-map.json").write_text(content)
    assert check_traceability(root)


def test_TR_F04_outside_path_is_rejected(trace):
    _, _, _, manifest = trace
    manifest["implemented"]["fixture/specs/auth/spec.md"]["AUTH-N01"]["test"] = (
        "../outside.py"
    )
    assert any("无效文件" in error for error in check(trace))


def test_TR_F02_TR_F04_script_must_be_executed_and_assertion_present(trace):
    root, _, test, manifest = trace
    script = root / "tests/runtime.py"
    script.write_text("assert 1 == 1\n")
    entry = manifest["implemented"]["fixture/specs/auth/spec.md"]["AUTH-N01"]
    entry.update(
        script="tests/runtime.py", runner="run_script", assertion="assert 1 == 1"
    )
    test.write_text(
        "def run_script(compose):\n"
        '    compose("exec", "-T", "app", "python", "-c", '
        'Path(__file__).with_name("runtime.py").read_text())\n'
        "def test_auth():\n"
        "    run_script(None)\n"
        "    assert True\n"
    )
    assert check(trace) == []
    script.write_text("def never_called():\n    assert 1 == 1\n")
    assert any("缺少脚本断言" in error for error in check(trace))
    script.write_text("assert 1 == 1\n")
    test.write_text(test.read_text().replace("    run_script(None)\n", ""))
    assert any("未调用脚本入口" in error for error in check(trace))


def test_TR_F03_missing_state_and_planned_reason_are_rejected(trace):
    root, _, _, manifest = trace
    other = root / "openspec/changes/future/specs/future/spec.md"
    other.parent.mkdir(parents=True)
    other.write_text("#### Scenario: FUTURE-N01 规划\n")
    assert any("未声明实现状态" in error for error in check(trace))
    manifest["planned"]["future/specs/future/spec.md"] = "未来功能待实现"
    assert any("缺少任务" in error for error in check(trace))
    (other.parents[2] / "tasks.md").write_text("- [ ] 实现未来能力\n")
    assert check(trace) == []


def test_TR_F03_pending_evidence_requires_open_task(trace):
    root, _, _, manifest = trace
    task = root / "openspec/changes/fixture/tasks.md"
    task.write_text("- [x] 1.1 已完成\n")
    manifest["implemented"]["fixture/specs/auth/spec.md"]["AUTH-N01"] = {
        "pending": "1.1",
        "task_file": "openspec/changes/fixture/tasks.md",
        "reason": "待专项验证",
    }
    assert any("未完成任务" in error for error in check(trace))
    task.write_text("- [ ] 1.1 待验证\n")
    assert check(trace) == []


@pytest.mark.parametrize("heading", ("缺少编号", "AUTH-N01 重复编号"))
def test_TR_F03_unidentified_or_duplicate_scenario_fails(trace, heading):
    _, spec, _, _ = trace
    spec.write_text(spec.read_text() + f"#### Scenario: {heading}\n")
    assert any("场景编号非法或重复" in error for error in check(trace))
