"""显式执行的实际时间演练；独立于常规集成，耗时约十三分钟。"""

import json
from pathlib import Path

from tests.integration.test_alert_https import certificate
from tests.integration.test_compose import (
    ROOT,
    install_configuration_client,
)
from tests.integration.test_compose import (
    stack as _stack,
)

stack = _stack


def test_L10_N05_L10_F05_real_time_skill_alert_drill(stack, tmp_path):
    compose, _, status, version = stack
    assert status("ready")[0] == 200
    compose("exec", "-T", "app", "python", "-m", "app.auth_admin", "upgrade")
    key, cert = certificate(tmp_path, "receiver")
    compose("exec", "-T", "app", "mkdir", "-p", "/tmp/scripts")
    for name in (
        "observability_dashboard.py",
        "observability_dashboard.html",
        "evaluate_skill_alerts.py",
        "deliver_skill_alerts.py",
        "watch_skill_alerts.py",
    ):
        compose("cp", str(ROOT / "scripts" / name), "app:/tmp/scripts/" + name)
    compose("cp", str(key), "app:/tmp/receiver.key")
    compose("cp", str(cert), "app:/tmp/receiver.crt")
    compose(
        "exec", "-T", "--user", "0", "app", "chown", "10001:10001", "/tmp/receiver.key"
    )
    compose(
        "cp",
        str(Path(__file__).with_name("skill_alert_drill.py")),
        "app:/tmp/skill_alert_drill.py",
    )
    compose(
        "cp",
        str(ROOT / "tests/integration/feedback_runtime.py"),
        "app:/tmp/feedback_runtime.py",
    )
    install_configuration_client(compose)
    output = compose(
        "exec",
        "-T",
        "-e",
        "CAMPUSCLAW_ALERT_DRILL=1",
        "app",
        "python",
        "-c",
        "import sys; sys.path.insert(0, '/tmp'); exec(sys.argv[1])",
        (ROOT / "tests/integration/ai_apps_runtime.py").read_text(),
        timeout=900,
    )
    report = json.loads(
        next(
            line.removeprefix("ALERT_DRILL ")
            for line in output.splitlines()
            if line.startswith("ALERT_DRILL ")
        )
    )
    assert report["version"] == version
    assert report["duration_seconds"] >= 690
    assert report["fault_requests"] >= 20 and report["success_requests"] >= 20
    assert report["notification_states"] == ["firing", "resolved"]
    assert report["failed_deliveries"] >= 1 and report["watcher_exit"] == 0
    target = ROOT / "reports/observability"
    target.mkdir(parents=True, exist_ok=True)
    compose("cp", "app:/tmp/alert-drill", str(tmp_path / "collected"))
    for name in ("report.json", "panel.html", "watch.jsonl"):
        (target / ("drill-" + name)).write_bytes(
            (tmp_path / "collected" / name).read_bytes()
        )
    print("ALERT_DRILL " + json.dumps(report, ensure_ascii=False))
