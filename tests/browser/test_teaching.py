"""显式运行：真实 Chromium、Docker 与一次性 MySQL。"""

import subprocess
import sys
from pathlib import Path


def test_SB_B02_browser_draft_survives_relogin():
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, str(root / "tests/browser/run_teaching.py")],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "TEACHING_BROWSER_RUNTIME_OK" in result.stdout
