import subprocess
import sys
from pathlib import Path

import pytest

RUNNER = Path(__file__).resolve().parents[2] / "scripts" / "check_pytest.py"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("def test_passes():\n    assert True\n", 0),
        ("", 5),
        ("import pytest\n@pytest.mark.skip\ndef test_skipped(): pass\n", 1),
        (
            "import pytest\n@pytest.mark.xfail\ndef test_expected_failure(): assert False\n",
            1,
        ),
        ("import pytest\n@pytest.mark.xfail\ndef test_unexpected_pass(): pass\n", 1),
        ("def test_fails():\n    assert False\n", 1),
    ],
    ids=("passing", "empty", "skip", "xfail", "xpass", "failing"),
)
def test_CK_N01_CK_F02_required_suite_exit_status(tmp_path, source, expected):
    (tmp_path / "test_sample.py").write_text(source)
    result = subprocess.run(
        [sys.executable, str(RUNNER), "-q"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == expected, result.stdout + result.stderr
    if "pytest.mark" in source:
        assert "工程门禁失败" in result.stdout


def test_CK_F02_shell_collection_only_cannot_hide_test_failure(tmp_path, monkeypatch):
    (tmp_path / "test_sample.py").write_text("def test_fails():\n    assert False\n")
    monkeypatch.setenv("PYTEST_ADDOPTS", "--collect-only")
    result = subprocess.run(
        [sys.executable, str(RUNNER), "-q"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "1 failed" in result.stdout
