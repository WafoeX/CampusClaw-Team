"""IO-F05：补偿有界、精确作用域、失败持久化与完成凭证再核对。"""

from unittest.mock import Mock

import pytest

from app.adapters.index_clients import IndexDependencyError
from app.services.access import AccessDenied
from app.services.index_cleanup import IndexCleanupService


def receipt(**changes):
    return {
        "id": "receipt",
        "class_id": "class-a",
        "material_id": "material-a",
        "source_version": 1,
        "index_version": 3,
        "index_config_version": "config",
        "status": "pending",
        "vector_collection": "registered-collection",
        "attempts": 0,
        **changes,
    }


def test_IO_F05_completed_receipt_is_rechecked_for_late_points():
    repository, vectors = Mock(), Mock()
    repository.candidates.return_value = [receipt(status="complete")]
    repository.claim.return_value = receipt(attempts=2)
    repository.manual_count.return_value = 0
    vectors.count.return_value = 1
    result = IndexCleanupService(
        repository, lambda name: vectors, RuntimeError, IndexDependencyError
    ).run()
    assert result == {"completed": 1, "failed": 0, "manual": 0}
    scope = vectors.delete.call_args.args[0]
    assert (
        scope.class_id == "class-a"
        and scope.material_id == "material-a"
        and scope.index_version == 3
    )
    repository.finish.assert_called_once_with(repository.claim.return_value, True)
    repository.touch_complete.assert_not_called()


def test_IO_F05_empty_completed_scope_not_deleted_again_or_charged_attempt():
    repository, vectors = Mock(), Mock()
    repository.candidates.return_value = [receipt(status="complete")]
    repository.manual_count.return_value = 0
    vectors.count.return_value = 0
    result = IndexCleanupService(
        repository, lambda name: vectors, RuntimeError, IndexDependencyError
    ).run()
    assert result["completed"] == 1
    repository.claim.assert_not_called()
    vectors.delete.assert_not_called()
    repository.touch_complete.assert_called_once_with("receipt")


def test_IO_F05_dependency_failure_is_persisted_and_reported():
    repository, vectors = Mock(), Mock()
    repository.candidates.return_value = [receipt()]
    repository.claim.return_value = receipt(attempts=1)
    repository.manual_count.return_value = 0
    vectors.delete.side_effect = IndexDependencyError("synthetic_unavailable")
    result = IndexCleanupService(
        repository, lambda name: vectors, RuntimeError, IndexDependencyError
    ).run()
    assert result["failed"] == 1 and result["completed"] == 0
    repository.finish.assert_called_once_with(repository.claim.return_value, False)


def test_IO_F05_cleanup_database_error_is_not_success():
    repository = Mock()
    repository.prune.side_effect = RuntimeError("synthetic_database")
    with pytest.raises(AccessDenied) as error:
        IndexCleanupService(
            repository, Mock(), RuntimeError, IndexDependencyError
        ).run()
    assert error.value.status == 503
