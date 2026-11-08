"""显式有界清理已过期同步记录和私有会话；无模型、文件或向量副作用。"""

import argparse
import json
import os

from app.adapters.ai_repository import AIRepository
from app.adapters.database import DatabaseError, mysql_engine
from app.services.auth import utc_now


def main():
    parser = argparse.ArgumentParser(description="清理过期AI执行数据和私有会话")
    parser.add_argument("action", choices=("cleanup",))
    parser.parse_args()
    engine = None
    try:
        engine = mysql_engine(
            host=os.environ["MYSQL_HOST"],
            port=int(os.environ["MYSQL_PORT"]),
            database=os.environ["MYSQL_DATABASE"],
            user=os.environ["MYSQL_USER"],
            password=os.environ["MYSQL_PASSWORD"],
        )
        print(json.dumps(AIRepository(engine).cleanup_expired(utc_now())))
    except (KeyError, ValueError, DatabaseError):
        parser.exit(1, "AI数据清理失败，请核对数据库和迁移状态。\n")
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    main()
