"""RT-N01/B01/F03–F06：范围前置、回表和输出前重验。"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.adapters.index_clients import IndexDependencyError
from app.services.access import AccessDenied, Identity
from app.services.index_scope import IndexScope
from app.services.retrieval import RetrievalService, rrf

IDENTITY = Identity("actor", "class-a", frozenset({"materials:read"}))
SCOPE = IndexScope("class-a", "material", 1, 1, "config")


def chunk(chunk_id="chunk-a"):
    return SCOPE.fields | {
        "id": chunk_id,
        "title": "合成资料",
        "start_offset": 0,
        "end_offset": 2,
        "content": "原文",
    }


def candidate():
    repository, embedding, vectors = Mock(), Mock(), Mock()
    actor = Mock(
        return_value=SimpleNamespace(id="actor", class_id="class-a", role="student")
    )
    repository.keyword.return_value = [chunk()]
    repository.authorized_chunks.return_value = [chunk()]
    repository.versions.return_value = [
        {
            "id": "material",
            "class_id": "class-a",
            "content_version": 1,
            "active_index_version": 1,
            "vector_ready": True,
        }
    ]
    repository.version_scope.return_value = SCOPE.fields
    vectors.query.return_value = [
        {"id": "chunk-a", "payload": SCOPE.payload("chunk-a")}
    ]
    service = RetrievalService(
        repository,
        RuntimeError,
        embedding,
        vectors,
        IndexDependencyError,
        actor,
        0.449357,
    )
    return service, repository, embedding, vectors, actor


def test_RT_N01_rrf_uses_rank_deduplicates_and_stably_breaks_ties():
    assert rrf(["a", "b"], ["b", "c"]) == ["b", "a", "c"]
    assert rrf(["a", "a", "b"], ["b", "c"]) == ["b", "a", "c"]


def test_RT_F04_keyword_never_calls_model_or_qdrant():
    service, repo, embedding, vectors, _ = candidate()
    result = service.search(IDENTITY, "synthetic", "原文", "keyword", None)
    assert result["items"][0]["text"] == "原文"
    assert not embedding.mock_calls and not vectors.mock_calls
    assert repo.authorized_chunks.call_args.args[0] == "class-a"


def test_RT_B01_empty_scope_still_checks_vector_health_without_unfiltered_query():
    service, repo, embedding, vectors, _ = candidate()
    repo.versions.return_value = []
    repo.authorized_chunks.return_value = []
    result = service.search(IDENTITY, "synthetic", "原文", "vector", None)
    assert result["items"] == []
    vectors.available.assert_called_once()
    vectors.query.assert_not_called()
    assert not embedding.mock_calls


def test_RT_F05_payload_mismatch_is_dropped_before_ranking():
    service, repo, _, vectors, _ = candidate()
    vectors.query.return_value = [
        {"id": "chunk-a", "payload": SCOPE.payload("chunk-a") | {"class_id": "class-b"}}
    ]
    repo.authorized_chunks.side_effect = [[chunk()], []]
    result = service.search(IDENTITY, "synthetic", "原文", "vector", None)
    assert result["items"] == []


def test_RT_F03_foreign_chapter_rejected_before_recall():
    service, repo, embedding, vectors, _ = candidate()
    repo.chapter_exists.return_value = False
    with pytest.raises(AccessDenied) as error:
        service.search(IDENTITY, "synthetic", "原文", "hybrid", "foreign-chapter")
    assert error.value.status == 404
    repo.keyword.assert_not_called()
    assert not embedding.mock_calls and not vectors.mock_calls


@pytest.mark.parametrize("mode", ["vector", "hybrid"])
def test_RT_F04_keyword_only_source_cannot_be_presented_as_complete_vector(mode):
    service, repo, _, vectors, _ = candidate()
    repo.versions.return_value = [{"id": "material", "vector_ready": False}]
    with pytest.raises(AccessDenied) as error:
        service.search(IDENTITY, "synthetic", "原文", mode, None)
    assert error.value.status == 503
    vectors.query.assert_not_called()


def test_RT_F05_rebuild_before_response_cannot_emit_stale_source():
    service, repo, _, _, _ = candidate()
    repo.authorized_chunks.return_value = []
    with pytest.raises(AccessDenied) as error:
        service.search(IDENTITY, "synthetic", "原文", "keyword", None)
    assert error.value.status == 409


def test_RT_F06_vector_failure_does_not_return_keyword_half_of_hybrid():
    service, _, _, vectors, _ = candidate()
    vectors.available.side_effect = IndexDependencyError("synthetic_down")
    with pytest.raises(AccessDenied) as error:
        service.search(IDENTITY, "synthetic", "原文", "hybrid", None)
    assert error.value.status == 503


def test_RT_F02_identity_is_revalidated_before_response():
    service, _, _, _, actor = candidate()
    actor.side_effect = [
        SimpleNamespace(id="actor", class_id="class-a", role="student"),
        None,
    ]
    with pytest.raises(AccessDenied) as error:
        service.search(IDENTITY, "synthetic", "原文", "keyword", None)
    assert error.value.status == 401


@pytest.mark.parametrize("stage", ["keyword", "authorized_chunks", "embedding"])
def test_RT_F06_database_or_embedding_failure_suppresses_partial_output(stage):
    service, repo, embedding, _, _ = candidate()
    if stage == "embedding":
        embedding.embed_query.side_effect = IndexDependencyError("timeout")
    else:
        getattr(repo, stage).side_effect = RuntimeError("synthetic database error")
    with pytest.raises(AccessDenied) as error:
        service.search(IDENTITY, "synthetic", "原文", "hybrid", None)
    assert error.value.status == 503 and error.value.code == 1500
