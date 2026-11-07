"""显式有界补偿；已完成凭证仍重查，覆盖迟到 upsert 与隔离恢复。"""

import time

from app.services.index_scope import IndexScope
from app.services.materials import unavailable


class IndexCleanupService:
    def __init__(
        self, repository, vectors_for_collection, database_error, dependency_error
    ):
        self.repository = repository
        self.vectors_for_collection = vectors_for_collection
        self.database_error = database_error
        self.dependency_error = dependency_error

    def run(self):
        deadline = time.monotonic() + 35
        completed = failed = 0
        try:
            self.repository.prune()
            for candidate in self.repository.candidates():
                if time.monotonic() >= deadline:
                    break
                scope = IndexScope(
                    *(
                        candidate[key]
                        for key in (
                            "class_id",
                            "material_id",
                            "source_version",
                            "index_version",
                            "index_config_version",
                        )
                    )
                )
                # 完成记录保留并复核；无残留的复核不消耗新的删除尝试。
                if candidate["status"] == "complete" and candidate["vector_collection"]:
                    try:
                        vectors = self.vectors_for_collection(
                            candidate["vector_collection"]
                        )
                        if vectors.count(scope, deadline) == 0:
                            self.repository.touch_complete(candidate["id"])
                            completed += 1
                            continue
                    except self.dependency_error:
                        pass
                row = self.repository.claim(candidate["id"])
                if row is None:
                    continue
                try:
                    vectors = self.vectors_for_collection(row["vector_collection"])
                    vectors.delete(scope, deadline)
                except self.dependency_error:
                    self.repository.finish(row, False)
                    failed += 1
                else:
                    self.repository.finish(row, True)
                    completed += 1
            return {
                "completed": completed,
                "failed": failed,
                "manual": self.repository.manual_count(),
            }
        except self.database_error:
            raise unavailable() from None
