"""MySQL 构建、Qdrant 点与清理凭证共用的精确版本作用域。"""

import json
from dataclasses import dataclass
from hashlib import sha256


@dataclass(frozen=True)
class IndexScope:
    class_id: str
    material_id: str
    source_version: int
    index_version: int
    index_config_version: str

    @property
    def fields(self):
        return {
            "class_id": self.class_id,
            "material_id": self.material_id,
            "source_version": self.source_version,
            "index_version": self.index_version,
            "index_config_version": self.index_config_version,
        }

    @property
    def key(self):
        return sha256(json.dumps(self.fields, sort_keys=True).encode()).hexdigest()

    def payload(self, chunk_id):
        return {**self.fields, "scope_key": self.key, "chunk_id": chunk_id}
