"""Task 5.1：一键命令保留失败退出码，HTML不复制敏感诊断。"""

from types import SimpleNamespace

from apitest import run_all


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
