"""PSC-N02/F06/F07/F09：扫描失败仍保留其他范围的判定。"""

from argparse import Namespace

from scripts import check_security as gate


def test_PSC_N02_PSC_F06_PSC_F07_PSC_F09_scans_continue_and_redact(
    tmp_path, monkeypatch, capsys
):
    revision = "a" * 40
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "revision").write_text(revision)
    (assets / "app.tar").write_bytes(b"synthetic image fixture")
    for scope, names in gate.FILES.items():
        (assets / scope).mkdir()
        for name in names:
            (assets / scope / name).write_text("synthetic test fixture")
    # 保留目录及其他产物，但故意缺一件页面。
    (assets / "frontend" / "openapi.json").unlink()
    cache = tmp_path / "cache"
    (cache / "db").mkdir(parents=True)
    (cache / "db" / "metadata.json").write_text(
        '{"Version":2,"UpdatedAt":"fixture","NextUpdate":"2099-01-01T00:00:00Z"}'
    )
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    commands = []

    def fake_git(*args):
        return {
            "rev-parse": b"false" if "shallow" in args[-1] else revision.encode(),
            "rev-list": b"12",
            "show": b"fixture lock",
            "ls-files": b"",
            "cat-file": b"",
        }[args[0]]

    def scanner(image, mounts, args, output):
        commands.append(args[0])
        if args[0] == "git":
            return 0, [{"Secret": "SYNTHETIC_NEVER_PRINT"}]
        if args[0] == "dir":
            return 0, []
        if args[0] == "fs":
            return 0, {
                "ArtifactName": "lock",
                "Results": [{"Vulnerabilities": [{"Severity": "HIGH"}]}],
            }
        return 125, None

    monkeypatch.setattr(gate, "git", fake_git)
    monkeypatch.setattr(gate, "docker_json", scanner)
    monkeypatch.setattr(gate, "image_matches", lambda path, candidate: True)
    monkeypatch.setattr(gate.subprocess, "run", lambda *args, **kwargs: None)
    options = Namespace(
        assets=assets,
        cache=cache,
        candidate=revision,
        gitleaks="fixture",
        trivy="fixture",
    )
    assert gate.run_checks(options, scratch) == 1
    assert commands == ["git", "dir", "dir", "fs", "image"]
    stdout = capsys.readouterr().out
    assert "SYNTHETIC_NEVER_PRINT" not in stdout
    for result in (
        '"scope": "history", "exit": 1, "secrets": 1',
        '"scope": "frontend", "exit": 2',
        '"scope": "dependencies", "exit": 1, "high": 1, "critical": 0',
        '"scope": "app.tar", "exit": 2, "tool_exit": 125',
        '"scope": "mcp-server.tar", "exit": 2',
    ):
        assert result in stdout
