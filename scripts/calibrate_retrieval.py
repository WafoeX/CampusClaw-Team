"""只读环境密钥，一批合成嵌入校准；不输出向量或凭据。"""

import json
import math
import os
import time
from pathlib import Path

from app.adapters.index_clients import EmbeddingClient
from app.config import EmbeddingSettings


def cosine(left, right):
    return sum(a * b for a, b in zip(left, right, strict=True)) / math.sqrt(
        sum(a * a for a in left) * sum(b * b for b in right)
    )


def main():
    fixture = Path("tests/eval/retrieval-tuning.json")
    data = json.loads(fixture.read_text())
    config = EmbeddingSettings.load(os.environ)
    if config is None:
        raise SystemExit("缺少嵌入配置")
    materials = data["materials"]
    queries = data["positive_queries"] + data["negative_queries"]
    vectors = EmbeddingClient(config).embed(materials + queries, time.monotonic() + 35)
    source = vectors[: len(materials)]
    scores = [
        [cosine(query, part) for part in source] for query in vectors[len(materials) :]
    ]
    positive = [scores[index][index] for index in range(len(materials))]
    negative = [max(row) for row in scores[len(materials) :]]
    if min(positive) <= max(negative):
        raise SystemExit(
            "调参样例未形成可区分区间；须保留结果并继续独立校准，不发布阈值"
        )
    threshold = round((min(positive) + max(negative)) / 2, 6)
    report = {
        "fixture": data["version"],
        "requested_model": config.model,
        "response_model": "网关未提供",
        "dimension": config.dimension,
        "positive_scores": positive,
        "negative_max_scores": negative,
        "threshold": threshold,
        "recall_per_route": 20,
        "result_limit": 8,
        "rrf_k": 60,
        "samples": len(queries),
        "final_evaluation": False,
    }
    output = Path("reports/2026-11-06-index-builds/retrieval-calibration.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
