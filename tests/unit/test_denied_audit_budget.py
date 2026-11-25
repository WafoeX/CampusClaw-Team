"""DAB 的并发上限、时间边界和进程预算隔离。"""

from concurrent.futures import ThreadPoolExecutor

import pytest

from app.config import ConfigError, Settings
from app.services.denied_audit_budget import DeniedAuditBudget, DeniedAuditResult


def test_DAB_B01_concurrent_subject_and_global_caps():
    budget = DeniedAuditBudget(per_subject=2, total=3, clock=lambda: 10)
    subjects = ["a"] * 100 + ["b"] * 100 + [f"other-{i}" for i in range(100)]
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(budget.reserve, subjects))
    admitted = [
        subject
        for subject, result in zip(subjects, results, strict=True)
        if result is None
    ]
    assert len(admitted) == 3
    assert all(admitted.count(subject) <= 2 for subject in admitted)
    assert results.count(DeniedAuditResult.LIMIT_REACHED) == 1
    assert results.count(DeniedAuditResult.SUPPRESSED) == 296
    assert len(budget._subjects) <= 3


def test_DAB_B02_exact_window_boundary_and_instance_isolation():
    now = [59.999]
    budget = DeniedAuditBudget(1, 1, clock=lambda: now[0])
    assert budget.reserve("old") is None
    assert budget.reserve("old") is DeniedAuditResult.LIMIT_REACHED
    assert budget.reserve("other") is DeniedAuditResult.SUPPRESSED
    independent = DeniedAuditBudget(1, 1, clock=lambda: now[0])
    assert independent.reserve("old") is None
    now[0] = 60
    assert budget.reserve("new") is None
    assert budget._subjects == {"new": 1}
    assert budget.reserve("new") is DeniedAuditResult.LIMIT_REACHED
    now[0] = 180
    assert budget.reserve("third") is None
    assert budget._subjects == {"third": 1}


@pytest.mark.parametrize(
    "key", ["AUDIT_DENIED_SUBJECT_LIMIT", "AUDIT_DENIED_GLOBAL_LIMIT"]
)
@pytest.mark.parametrize(
    "value", ["", "0", "-1", "1.5", "NaN", " 60", "10001", "６０", "1" * 100]
)
def test_DAB_F01_invalid_budget_fails_without_disclosing_value(
    config_env, tmp_path, key, value
):
    metadata = tmp_path / "BUILD_VERSION"
    metadata.write_text("test-build")
    with pytest.raises(ConfigError) as error:
        Settings.load(config_env | {key: value}, metadata)
    assert str(error.value) == key


def test_DAB_F01_subject_exceeds_total_and_valid_configuration(config_env, tmp_path):
    metadata = tmp_path / "BUILD_VERSION"
    metadata.write_text("test-build")
    limits = {"AUDIT_DENIED_SUBJECT_LIMIT": "3", "AUDIT_DENIED_GLOBAL_LIMIT": "2"}
    with pytest.raises(ConfigError, match="^AUDIT_DENIED_SUBJECT_LIMIT$"):
        Settings.load(config_env | limits, metadata)
    limits["AUDIT_DENIED_SUBJECT_LIMIT"] = "2"
    loaded = Settings.load(config_env | limits, metadata)
    assert (loaded.audit_denied_subject_limit, loaded.audit_denied_global_limit) == (
        2,
        2,
    )
    defaults = Settings.load(config_env, metadata)
    assert (
        defaults.audit_denied_subject_limit,
        defaults.audit_denied_global_limit,
    ) == (60, 600)
