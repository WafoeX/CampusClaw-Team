import argparse
import os

from werkzeug.security import generate_password_hash

from app.adapters.auth_repository import AuthRepository
from app.adapters.database import DatabaseError, mysql_engine
from app.adapters.migrations.runner import migrate


def main():
    parser = argparse.ArgumentParser(description="管理 CampusClaw 认证数据库")
    parser.add_argument("action", choices=("upgrade", "downgrade", "seed"))
    args = parser.parse_args()
    database = os.environ.get("MYSQL_DATABASE", "")
    if args.action in {"seed", "downgrade"} and (
        os.environ.get("CAMPUSCLAW_ISOLATED_DATABASE") != "1"
        or not database.startswith("campusclaw_test_")
    ):
        parser.error("该命令仅允许用于明确登记的隔离测试库")
    try:
        engine = mysql_engine(
            host=os.environ["MYSQL_HOST"],
            port=int(os.environ["MYSQL_PORT"]),
            database=os.environ["MYSQL_DATABASE"],
            user=os.environ["MYSQL_USER"],
            password=os.environ["MYSQL_PASSWORD"],
        )
        try:
            if args.action == "seed":
                password = os.environ["CAMPUSCLAW_SEED_PASSWORD"]
                if not 1 <= len(password.encode("utf-8")) <= 128:
                    raise ValueError
                password_hash = generate_password_hash(password, method="scrypt")
                AuthRepository(engine).seed_demo_accounts(password_hash)
            else:
                migrate(engine, downgrade=args.action == "downgrade")
        finally:
            engine.dispose()
    except (KeyError, ValueError, DatabaseError):
        parser.exit(1, "认证数据库命令失败，请核对隔离配置、库权限和迁移状态。\n")


if __name__ == "__main__":
    main()
