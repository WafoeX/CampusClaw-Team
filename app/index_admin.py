"""仅运维可执行的有界索引恢复；不输出正文、身份或凭据。"""

import argparse
import json
import os
from pathlib import Path

from app.adapters.database import DatabaseError, mysql_engine
from app.adapters.index_cleanup_repository import IndexCleanupRepository
from app.adapters.index_clients import IndexDependencyError, QdrantIndexClient
from app.adapters.index_repository import IndexRepository
from app.config import ConfigError, Settings
from app.services.access import AccessDenied
from app.services.index_cleanup import IndexCleanupService
from app.services.indexing import IndexService


def main():
    parser = argparse.ArgumentParser(description="每批恢复最多 100 个过期索引构建")
    parser.add_argument("action", choices=("recover", "cleanup"))
    args = parser.parse_args()
    try:
        settings = Settings.load(os.environ, Path(__file__).with_name("BUILD_VERSION"))
        engine = mysql_engine(
            host=settings.mysql_host,
            port=settings.mysql_port,
            database=settings.mysql_database,
            user=settings.mysql_user,
            password=settings.mysql_password,
        )
        try:
            if args.action == "recover":
                service = IndexService(
                    IndexRepository(engine),
                    DatabaseError,
                    None,
                    None,
                    IndexDependencyError,
                    "recovery-only",
                )
                print(f"已处理过期构建：{service.recover()}")
            else:
                if settings.embedding is None:
                    raise ConfigError("EMBEDDING_MODEL")
                cleaner = IndexCleanupService(
                    IndexCleanupRepository(engine),
                    lambda collection: QdrantIndexClient(
                        settings.qdrant_url,
                        settings.qdrant_api_key,
                        settings.embedding,
                        collection=collection,
                    ),
                    DatabaseError,
                    IndexDependencyError,
                )
                result = cleaner.run()
                print(json.dumps(result))
                if result["failed"] or result["manual"]:
                    parser.exit(1, "索引清理仍有失败或待人工处理项。\n")
        finally:
            engine.dispose()
    except (ConfigError, DatabaseError, AccessDenied):
        parser.exit(1, "索引恢复失败，请核对数据库与迁移状态。\n")


if __name__ == "__main__":
    main()
