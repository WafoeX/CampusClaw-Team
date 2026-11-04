"""Run a required test suite and reject skipped cases."""

import os
import sys

import pytest


class RequiredCases:
    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(self, session, exitstatus):
        terminal = session.config.pluginmanager.get_plugin("terminalreporter")
        if terminal is None:
            session.exitstatus = pytest.ExitCode.INTERNAL_ERROR
            return
        if exitstatus != pytest.ExitCode.OK:
            return
        skipped = sum(
            len(terminal.stats.get(result, ()))
            for result in ("skipped", "xfailed", "xpassed")
        )
        if skipped:
            terminal.write_line(
                f"工程门禁失败：{skipped} 项必需测试被跳过或标为预期失败。"
            )
            session.exitstatus = pytest.ExitCode.TESTS_FAILED
        elif not terminal.stats.get("passed"):
            terminal.write_line("工程门禁失败：没有执行通过的测试。")
            session.exitstatus = pytest.ExitCode.NO_TESTS_COLLECTED


if __name__ == "__main__":
    # The gate must run the suite selected by the repository, regardless of shell defaults.
    os.environ.pop("PYTEST_ADDOPTS", None)
    raise SystemExit(pytest.main(sys.argv[1:], plugins=[RequiredCases()]))
