"""IX-N01/B01/F04：构建外部边界的确定性回归，完整发布场景仍待接入。"""

import time
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.adapters.index_clients import (
    EmbeddingClient,
    IndexDependencyError,
    JsonEndpoint,
    QdrantIndexClient,
    validate_vector,
)
from app.config import ConfigError, EmbeddingSettings
from app.services.index_scope import IndexScope

CONFIG = EmbeddingSettings(
    "https://ai-gateway.devops.hello1023.com/v1",
    "synthetic-value",
    "course-embedding",
    2048,
)
SCOPE = IndexScope("class-a", "material-a", 1, 1, "configuration")
CHUNK = SimpleNamespace(id="chunk-a")


def deadline():
    return time.monotonic() + 35


def test_IX_N01_embedding_config_has_stable_nonsecret_collection():
    assert CONFIG.version == replace(CONFIG, api_key="another-synthetic-value").version
    assert CONFIG.collection != replace(CONFIG, dimension=3).collection
    assert "synthetic" not in repr(CONFIG)
    assert EmbeddingSettings.load({}) is None
    loaded = EmbeddingSettings.load(
        {
            "EMBEDDING_BASE_URL": CONFIG.base_url,
            "EMBEDDING_MODEL": CONFIG.model,
            "EMBEDDING_DIM": "2048",
            "EMBEDDING_API_KEY": "",
        }
    )
    assert loaded.api_key == "" and loaded.dimension == 2048


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("EMBEDDING_BASE_URL", "http://127.0.0.1/v1"),
        ("EMBEDDING_BASE_URL", "https://ai-gateway.devops.hello1023.com.evil/v1"),
        ("EMBEDDING_MODEL", "unregistered-model"),
        ("EMBEDDING_DIM", "0"),
        ("EMBEDDING_DIM", "2048.0"),
        ("EMBEDDING_API_KEY", "synthetic\nvalue"),
    ],
)
def test_IX_F04_config_rejects_unregistered_or_header_injection(field, value):
    env = {
        "EMBEDDING_BASE_URL": CONFIG.base_url,
        "EMBEDDING_MODEL": CONFIG.model,
        "EMBEDDING_DIM": "2048",
        "EMBEDDING_API_KEY": "synthetic-value",
    }
    with pytest.raises(ConfigError, match="^" + field + "$"):
        EmbeddingSettings.load({**env, field: value})


@pytest.mark.parametrize(
    "vector",
    [
        [],
        [True, 1],
        [float("nan"), 1],
        [float("inf"), 1],
        [1e300, 1],
        [0, 0],
        ["1", 1],
        {"0": 1},
        [1, 2, 3],
    ],
)
def test_IX_F04_invalid_vector_rejected(vector):
    with pytest.raises(IndexDependencyError):
        validate_vector(vector, 2)


def test_IX_N01_embedding_response_reordered_by_index_and_batch_is_bounded():
    endpoint = Mock()
    endpoint.request.return_value = {
        "model": CONFIG.model,
        "data": [
            {"index": 1, "embedding": [2.0] * 2048},
            {"index": 0, "embedding": [1.0] * 2048},
        ],
    }
    client = EmbeddingClient(CONFIG, endpoint=endpoint)
    vectors = client.embed(["甲", "乙"], deadline())
    assert vectors[0][0] == 1 and vectors[1][0] == 2
    assert endpoint.request.call_args.args[2] == {
        "model": CONFIG.model,
        "input": ["甲", "乙"],
    }
    endpoint.reset_mock()
    for texts in ([], ["正文"] * 33, [" "], ["字"] + ["字" * 1201]):
        with pytest.raises(IndexDependencyError):
            client.embed(texts, deadline())
    endpoint.request.assert_not_called()
    with pytest.raises(IndexDependencyError, match="embedding_config"):
        EmbeddingClient(replace(CONFIG, api_key=""), endpoint=endpoint).embed(
            ["甲"], deadline()
        )
    endpoint.request.assert_not_called()


def test_IX_N01_course_gateway_omits_optional_model_metadata():
    endpoint = Mock()
    endpoint.request.return_value = {"data": [{"index": 0, "embedding": [1.0] * 2048}]}
    vectors = EmbeddingClient(CONFIG, endpoint=endpoint).embed(["合成资料"], deadline())
    assert len(vectors[0]) == 2048
    assert endpoint.request.call_args.args[2]["model"] == "course-embedding"


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"model": "wrong", "data": []},
        {"model": CONFIG.model, "data": [{"index": 0, "embedding": [1.0] * 2048}] * 2},
        {"model": CONFIG.model, "data": [{"index": True, "embedding": [1.0] * 2048}]},
        {"model": CONFIG.model, "data": [{"index": 0, "embedding": [1.0]}]},
        {"model": CONFIG.model, "data": [None]},
    ],
)
def test_IX_F04_embedding_malformed_response_not_retried(response):
    endpoint = Mock()
    endpoint.request.return_value = response
    sleeper = Mock()
    with pytest.raises(IndexDependencyError):
        EmbeddingClient(CONFIG, endpoint=endpoint, sleep=sleeper).embed(
            ["甲"], deadline()
        )
    assert endpoint.request.call_count == 1
    sleeper.assert_not_called()


def test_IX_F04_only_transient_embedding_retried_once_with_total_deadline():
    endpoint, sleeper = Mock(), Mock()
    endpoint.request.side_effect = IndexDependencyError("http", transient=True)
    with pytest.raises(IndexDependencyError):
        EmbeddingClient(CONFIG, endpoint=endpoint, sleep=sleeper).embed(
            ["甲"], deadline()
        )
    assert endpoint.request.call_count == 2
    sleeper.assert_called_once_with(1)
    endpoint.reset_mock()
    with pytest.raises(IndexDependencyError):
        EmbeddingClient(CONFIG, endpoint=endpoint, sleep=sleeper).embed(
            ["甲"], time.monotonic() - 1
        )
    endpoint.request.assert_not_called()


def test_IX_N01_point_write_and_exact_readback_contract():
    endpoint = Mock()
    client = QdrantIndexClient(
        "http://qdrant:6333", "synthetic-value", CONFIG, endpoint=endpoint
    )
    client.write(SCOPE, [CHUNK], [[1.0] * 2048], deadline())
    args = endpoint.request.call_args.args
    assert args[0] == "PUT" and args[1].endswith("/points?wait=true")
    assert args[2]["points"][0]["payload"] == SCOPE.payload(CHUNK.id)
    assert "content" not in args[2]["points"][0]["payload"]
    endpoint.request.return_value = {
        "result": {
            "points": [
                {
                    "id": CHUNK.id,
                    "payload": SCOPE.payload(CHUNK.id),
                    "vector": [1.0] * 2048,
                }
            ],
            "next_page_offset": None,
        }
    }
    client.verify(SCOPE, [CHUNK], deadline())
    assert endpoint.request.call_args.args[2]["filter"] == client.scope_filter(SCOPE)


@pytest.mark.parametrize("mutation", ["extra", "payload", "id", "dimension", "next"])
def test_IX_F04_readback_refuses_mismatched_or_partial_points(mutation):
    row = {"id": CHUNK.id, "payload": SCOPE.payload(CHUNK.id), "vector": [1.0] * 2048}
    page = {"points": [row], "next_page_offset": None}
    if mutation == "extra":
        page["points"].append(dict(row))
    elif mutation == "payload":
        row["payload"]["class_id"] = "class-b"
    elif mutation == "id":
        row["id"] = "unknown"
    elif mutation == "dimension":
        row["vector"] = [1.0]
    else:
        page["next_page_offset"] = "next"
    endpoint = Mock()
    endpoint.request.return_value = {"result": page}
    client = QdrantIndexClient(
        "http://qdrant:6333", "synthetic", CONFIG, endpoint=endpoint
    )
    with pytest.raises(IndexDependencyError):
        client.verify(SCOPE, [CHUNK], deadline())


def test_IX_F04_collection_existing_mismatch_is_never_overwritten():
    endpoint = Mock()
    endpoint.request.side_effect = [
        {"result": {"collections": [{"name": CONFIG.collection}]}},
        {
            "result": {
                "config": {"params": {"vectors": {"size": 2, "distance": "Cosine"}}}
            }
        },
    ]
    with pytest.raises(IndexDependencyError, match="collection_config"):
        QdrantIndexClient(
            "http://qdrant:6333", "synthetic", CONFIG, endpoint=endpoint
        ).ensure_collection(deadline())
    assert all(call.args[0] == "GET" for call in endpoint.request.call_args_list)


def test_IX_F04_transport_redirect_does_not_forward_credentials_or_read_error_body():
    connection = Mock()
    connection.getresponse.return_value.status = 302
    factory = Mock(return_value=connection)
    endpoint = JsonEndpoint(
        CONFIG.base_url,
        {"Authorization": "Bearer synthetic"},
        connection_factory=factory,
    )
    with pytest.raises(IndexDependencyError, match="http"):
        endpoint.request("POST", "/embeddings", {"input": ["甲"]}, deadline())
    factory.assert_called_once()
    connection.getresponse.return_value.read1.assert_not_called()
    connection.close.assert_called_once()
