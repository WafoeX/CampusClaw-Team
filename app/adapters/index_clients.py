"""有界 JSON 传输、课程嵌入与 Qdrant 精确版本写入；不记录正文或密钥。"""

import json
import math
import re
import time
from http.client import HTTPConnection, HTTPException, HTTPSConnection
from urllib.parse import urlsplit


class IndexDependencyError(Exception):
    def __init__(self, stage, *, transient=False):
        super().__init__(stage)
        self.stage = stage
        self.transient = transient


def remaining(deadline, clock=time.monotonic):
    seconds = deadline - clock()
    if seconds <= 0:
        raise IndexDependencyError("deadline")
    return min(15.0, seconds)


class JsonEndpoint:
    """地址来自部署配置；http.client 不跟随重定向，不读取代理环境。"""

    def __init__(self, base_url, headers, *, connection_factory=None):
        self.address = urlsplit(base_url)
        self.headers = dict(headers)
        self.connection_factory = connection_factory

    def request(self, method, path, payload, deadline):
        address = self.address
        factory = self.connection_factory or (
            HTTPSConnection if address.scheme == "https" else HTTPConnection
        )
        connection = factory(
            address.hostname, address.port, timeout=remaining(deadline)
        )
        try:
            body = None if payload is None else json.dumps(payload, allow_nan=False)
            connection.request(
                method,
                address.path.rstrip("/") + path,
                body=body,
                headers={"Content-Type": "application/json", **self.headers},
            )
            remaining(deadline)
            response = connection.getresponse()
            status = response.status
            if not 200 <= status < 300:
                # 不回传服务端响应体，尤其不把上游错误中的输入或凭据写入日志。
                raise IndexDependencyError(
                    "http", transient=status in (408, 429, 500, 502, 503, 504)
                )
            parts, size = [], 0
            while True:
                if connection.sock is not None:
                    connection.sock.settimeout(remaining(deadline))
                block = response.read1(65536)
                remaining(deadline)
                if not block:
                    break
                size += len(block)
                if size > 4 * 1024 * 1024:
                    raise IndexDependencyError("response_size")
                parts.append(block)
            result = json.loads(b"".join(parts))
            if not isinstance(result, dict):
                raise IndexDependencyError("structure")
            return result
        except (OSError, HTTPException):
            raise IndexDependencyError("transport", transient=True) from None
        except (ValueError, UnicodeError):
            raise IndexDependencyError("structure") from None
        finally:
            connection.close()


def validate_vector(vector, dimension):
    if (
        not isinstance(vector, list)
        or len(vector) != dimension
        or any(
            type(value) not in (int, float)
            or abs(value) > 3.4028235e38
            or not math.isfinite(value)
            for value in vector
        )
        or not any(vector)
    ):
        raise IndexDependencyError("vector")
    return vector


class EmbeddingClient:
    def __init__(self, config, *, endpoint=None, sleep=time.sleep, on_result=None):
        self.config = config
        self.endpoint = endpoint or JsonEndpoint(
            config.base_url, {"Authorization": f"Bearer {config.api_key}"}
        )
        self.sleep = sleep
        self.on_result = on_result or (lambda **details: None)

    def embed_query(self, text, deadline, *, before_call=None):
        return self.embed(
            [text], deadline, before_call=before_call, _max_characters=4000
        )[0]

    def embed(self, texts, deadline, *, before_call=None, _max_characters=1200):
        started = time.monotonic()
        if (
            not 1 <= len(texts) <= 32
            or any(not isinstance(value, str) or not value.strip() for value in texts)
            or any(len(value) > _max_characters for value in texts)
        ):
            raise IndexDependencyError("input")
        if not self.config.api_key:
            raise IndexDependencyError("embedding_config")
        for attempt in range(2):
            remaining(deadline)
            if before_call is not None:
                before_call()
            try:
                result = self.endpoint.request(
                    "POST",
                    "/embeddings",
                    {"model": self.config.model, "input": texts},
                    deadline,
                )
                break
            except IndexDependencyError as error:
                if not error.transient or attempt or remaining(deadline) <= 1:
                    raise
                self.sleep(1)
        try:
            rows = result["data"]
            if (
                ("model" in result and result["model"] != self.config.model)
                or not isinstance(rows, list)
                or len(rows) != len(texts)
                or any(type(row.get("index")) is not int for row in rows)
                or {row["index"] for row in rows} != set(range(len(texts)))
            ):
                raise IndexDependencyError("embedding_structure")
            vectors = [
                validate_vector(row["embedding"], self.config.dimension)
                for row in sorted(rows, key=lambda item: item["index"])
            ]
            usage = result.get("usage", {})
            tokens = (
                {
                    key: value
                    for key, value in usage.items()
                    if key in ("prompt_tokens", "total_tokens")
                    and type(value) is int
                    and 0 <= value <= 10_000_000
                }
                if isinstance(usage, dict)
                else {}
            )
            self.on_result(
                stage="embedding",
                model=self.config.model,
                model_config=self.config.version,
                dimension=self.config.dimension,
                response_model_present="model" in result,
                duration_ms=round((time.monotonic() - started) * 1000, 2),
                **tokens,
            )
            return vectors
        except (KeyError, TypeError, AttributeError):
            raise IndexDependencyError("embedding_structure") from None


class QdrantIndexClient:
    def __init__(self, url, api_key, config, *, endpoint=None, collection=None):
        self.config = config
        self.endpoint = endpoint or JsonEndpoint(url, {"api-key": api_key})
        name = collection or config.collection
        if not re.fullmatch(r"campusclaw_[a-f0-9]{64}", name):
            raise IndexDependencyError("collection_name")
        self.path = f"/collections/{name}"

    def ensure_collection(self, deadline):
        # PUT 对已有集合可能返回冲突，先读列表；不覆盖已有集合配置。
        response = self.endpoint.request("GET", "/collections", None, deadline)
        try:
            names = {item["name"] for item in response["result"]["collections"]}
        except (KeyError, TypeError):
            raise IndexDependencyError("collection_structure") from None
        if self.config.collection not in names:
            try:
                self.endpoint.request(
                    "PUT",
                    self.path,
                    {"vectors": {"size": self.config.dimension, "distance": "Cosine"}},
                    deadline,
                )
            except IndexDependencyError:
                # 另一进程可能已创建，随后的读取仍须逐项校验。
                self.check_collection(deadline)
        self.check_collection(deadline)
        for field in (
            "class_id",
            "material_id",
            "chunk_id",
            "scope_key",
            "index_config_version",
        ):
            self.endpoint.request(
                "PUT",
                self.path + "/index?wait=true",
                {"field_name": field, "field_schema": "keyword"},
                deadline,
            )

        for field in ("source_version", "index_version"):
            self.endpoint.request(
                "PUT",
                self.path + "/index?wait=true",
                {"field_name": field, "field_schema": "integer"},
                deadline,
            )

    def available(self, deadline):
        result = self.endpoint.request("GET", "/collections", None, deadline)
        body = result.get("result")
        if not isinstance(body, dict) or not isinstance(body.get("collections"), list):
            raise IndexDependencyError("collection_structure")

    def query(self, class_id, scopes, vector, threshold, deadline):
        if not 1 <= len(scopes) <= 1000 or any(
            scope.class_id != class_id for scope in scopes
        ):
            raise IndexDependencyError("query_scope")
        result = self.endpoint.request(
            "POST",
            self.path + "/points/query",
            {
                "query": validate_vector(vector, self.config.dimension),
                "filter": {
                    "must": [
                        {"key": "class_id", "match": {"value": class_id}},
                        {
                            "key": "scope_key",
                            "match": {"any": [scope.key for scope in scopes]},
                        },
                    ]
                },
                "limit": 20,
                "score_threshold": threshold,
                "with_payload": True,
            },
            deadline,
        )
        try:
            rows = result["result"]["points"]
            if (
                not isinstance(rows, list)
                or len(rows) > 20
                or any(
                    not isinstance(row, dict)
                    or type(row.get("id")) not in (str, int)
                    or type(row.get("score")) not in (int, float)
                    or abs(row["score"]) > 1.000001
                    or not math.isfinite(row["score"])
                    for row in rows
                )
            ):
                raise IndexDependencyError("query_structure")
            return sorted(
                [
                    dict(row, id=str(row["id"]))
                    for row in rows
                    if row["score"] >= threshold
                ],
                key=lambda row: (-row["score"], row["id"]),
            )
        except (KeyError, TypeError):
            raise IndexDependencyError("query_structure") from None

    def check_collection(self, deadline):
        result = self.endpoint.request("GET", self.path, None, deadline)
        try:
            vector = result["result"]["config"]["params"]["vectors"]
            valid = (
                vector["size"] == self.config.dimension
                and vector["distance"] == "Cosine"
            )
        except (KeyError, TypeError):
            valid = False
        if not valid:
            raise IndexDependencyError("collection_config")

    @staticmethod
    def scope_filter(scope):
        return {
            "must": [
                {"key": "class_id", "match": {"value": scope.class_id}},
                {"key": "scope_key", "match": {"value": scope.key}},
            ]
        }

    def write(self, scope, chunks, vectors, deadline):
        if not 1 <= len(chunks) <= 32 or len(chunks) != len(vectors):
            raise IndexDependencyError("point_count")
        points = [
            {
                "id": chunk.id,
                "payload": scope.payload(chunk.id),
                "vector": validate_vector(vector, self.config.dimension),
            }
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        self.endpoint.request(
            "PUT", self.path + "/points?wait=true", {"points": points}, deadline
        )

    def verify(self, scope, chunks, deadline):
        expected = {chunk.id: scope.payload(chunk.id) for chunk in chunks}
        if not 1 <= len(expected) <= 64 or len(expected) != len(chunks):
            raise IndexDependencyError("point_count")
        result = self.endpoint.request(
            "POST",
            self.path + "/points/scroll",
            {
                "filter": self.scope_filter(scope),
                "limit": 65,
                "with_payload": True,
                "with_vector": True,
            },
            deadline,
        )
        try:
            page = result["result"]
            rows = page["points"]
            if (
                page.get("next_page_offset") is not None
                or len(rows) != len(expected)
                or {row["id"] for row in rows} != set(expected)
                or any(row["payload"] != expected[row["id"]] for row in rows)
            ):
                raise IndexDependencyError("point_mismatch")
            for row in rows:
                validate_vector(row["vector"], self.config.dimension)
        except (KeyError, TypeError):
            raise IndexDependencyError("point_mismatch") from None

    def delete(self, scope, deadline):
        self.endpoint.request(
            "POST",
            self.path + "/points/delete?wait=true",
            {"filter": self.scope_filter(scope)},
            deadline,
        )
        if self.count(scope, deadline) != 0:
            raise IndexDependencyError("cleanup_remaining")

    def count(self, scope, deadline):
        result = self.endpoint.request(
            "POST",
            self.path + "/points/count",
            {"filter": self.scope_filter(scope), "exact": True},
            deadline,
        )
        try:
            count = result["result"]["count"]
            if type(count) is not int or count < 0:
                raise IndexDependencyError("cleanup_structure")
            return count
        except (KeyError, TypeError):
            raise IndexDependencyError("cleanup_structure") from None
