"""Task 5.1：一键命令保留失败退出码，HTML不复制敏感诊断。"""

import json
from types import SimpleNamespace

import pytest

from apitest import run_all


@pytest.fixture
def injection_manifest(monkeypatch, tmp_path):
    cases = tmp_path / "apitest/cases"
    cases.mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_fixture.py").write_text("def test_fixture(): pass\n")
    for scenario in run_all.INJECTION_SCENARIOS:
        (cases / (scenario + ".json")).write_text(
            json.dumps(
                {
                    "pytest": ["tests/test_fixture.py::test_fixture"],
                    "security_regression": {
                        "scenario": scenario,
                        "given": "隔离合成夹具",
                        "when": "提交反例",
                        "then": "拒绝且无写入",
                    },
                }
            )
        )
    monkeypatch.setattr(run_all, "ROOT", tmp_path)
    return cases


def test_SR_01_injection_manifest_collects_shared_cases_once(injection_manifest):
    (injection_manifest / "ordinary.json").write_text(
        json.dumps({"pytest": ["tests/test_fixture.py"]})
    )
    assert run_all.collect_nodes(injection=True) == [
        "tests/test_fixture.py::test_fixture"
    ]
    assert run_all.collect_nodes() == [
        "tests/test_fixture.py",
        "tests/test_fixture.py::test_fixture",
    ]


def test_SR_01_missing_injection_case_blocks_gate(injection_manifest):
    (injection_manifest / "SR-F08.json").unlink()
    with pytest.raises(ValueError, match="SR-F08"):
        run_all.collect_nodes()


@pytest.mark.parametrize("field", ["given", "when", "then", "scenario"])
def test_SR_01_incomplete_three_stage_case_blocks_gate(injection_manifest, field):
    path = injection_manifest / "SR-F07.json"
    entry = json.loads(path.read_text())
    entry["security_regression"][field] = " "
    path.write_text(json.dumps(entry))
    with pytest.raises(ValueError, match="三段式"):
        run_all.collect_nodes(injection=True)


def test_SR_01_missing_executable_case_blocks_gate(injection_manifest):
    path = injection_manifest / "SR-F09.json"
    entry = json.loads(path.read_text())
    entry["pytest"] = ["tests/missing.py::test_missing"]
    path.write_text(json.dumps(entry))
    with pytest.raises(ValueError, match="清单无效"):
        run_all.collect_nodes()


def test_ST_F04_apitest_failure_remains_nonzero(monkeypatch, tmp_path):
    monkeypatch.setattr(run_all, "REPORT", tmp_path)
    monkeypatch.setattr(
        run_all.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=1)
    )
    assert run_all.main() == 1
    assert "退出码：1" in (tmp_path / "index.html").read_text()


def test_ST_F03_apitest_html_excludes_failure_body(tmp_path):
    xml = tmp_path / "input.xml"
    xml.write_text(
        '<testsuite><testcase name="合成"><failure>private-response</failure><system-out>private-log</system-out></testcase></testsuite>'
    )
    target = tmp_path / "index.html"
    run_all.render_report(xml, target, 1)
    body = target.read_text()
    assert (
        "失败" in body and "private-response" not in body and "private-log" not in body
    )
