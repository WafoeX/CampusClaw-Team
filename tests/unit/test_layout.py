import pytest

from scripts import check_layout


def prepare_trace(root, location, *, tests=True):
    change = root / "openspec" / "changes" / location
    for capability, scenario in (
        ("skeleton-runtime", "RT-N01"),
        ("skeleton-access", "AC-F01"),
    ):
        spec = change / "specs" / capability / "spec.md"
        spec.parent.mkdir(parents=True)
        spec.write_text(f"#### Scenario: {scenario} 追溯样本\n")
    if tests:
        suite = root / "tests" / "test_trace.py"
        suite.parent.mkdir(exist_ok=True)
        suite.write_text("def test_RT_N01_AC_F01_trace(): pass\n")
    return change


@pytest.fixture
def trace_root(tmp_path, monkeypatch):
    monkeypatch.setattr(check_layout, "ROOT", tmp_path)
    monkeypatch.setattr(check_layout, "CHANGE_ROOT", tmp_path / "openspec" / "changes")
    return tmp_path


@pytest.mark.parametrize(
    "location",
    [
        check_layout.CHANGE,
        f"archive/{check_layout.CHANGE}",
        f"archive/2026-11-05-{check_layout.CHANGE}",
    ],
    ids=("active", "canonical-archive", "legacy-archive"),
)
def test_CK_N01_trace_survives_archive(trace_root, location):
    prepare_trace(trace_root, location)
    assert check_layout.check_scenarios() == []


def test_CK_F02_ambiguous_archives_are_rejected(trace_root):
    prepare_trace(trace_root, f"archive/{check_layout.CHANGE}")
    prepare_trace(trace_root, f"archive/2026-11-05-{check_layout.CHANGE}")
    assert check_layout.check_scenarios() == ["找不到唯一骨架规约"]


def test_CK_F02_archived_missing_test_is_rejected(trace_root):
    prepare_trace(trace_root, f"archive/{check_layout.CHANGE}", tests=False)
    assert check_layout.check_scenarios() == ["缺少用例 AC-F01", "缺少用例 RT-N01"]


def test_CK_F02_archived_missing_spec_is_rejected(trace_root):
    change = prepare_trace(trace_root, f"archive/{check_layout.CHANGE}")
    missing = change / "specs" / "skeleton-access" / "spec.md"
    missing.unlink()
    assert check_layout.check_scenarios() == [f"缺少规约 {missing}"]


def test_CK_F02_missing_change_is_rejected(trace_root):
    assert check_layout.check_scenarios() == ["找不到唯一骨架规约"]
