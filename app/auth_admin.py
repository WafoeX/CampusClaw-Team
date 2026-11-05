import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from werkzeug.security import generate_password_hash

from app.adapters.auth_repository import AuthRepository
from app.adapters.database import DatabaseError, mysql_engine
from app.adapters.material_repository import MaterialRepository
from app.adapters.migrations.runner import migrate


def _read_manifest(path):
    entries = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise ValueError
    result = []
    for entry in entries:
        if not isinstance(entry, dict) or entry.keys() != {"material_id", "deleted_at"}:
            raise ValueError
        material_id, deleted_at = entry["material_id"], entry["deleted_at"]
        if not isinstance(material_id, str) or not isinstance(deleted_at, str):
            raise ValueError
        date = datetime.fromisoformat(deleted_at)
        if str(UUID(material_id)) != material_id or date.utcoffset() != UTC.utcoffset(
            date
        ):
            raise ValueError
        result.append((material_id, date.replace(tzinfo=None)))
    return result


def main():
    parser = argparse.ArgumentParser(description="管理 CampusClaw 认证数据库")
    parser.add_argument(
        "action",
        choices=(
            "upgrade",
            "downgrade",
            "seed",
            "export-deletions",
            "replay-deletions",
        ),
    )
    parser.add_argument("--manifest")
    args = parser.parse_args()
    database = os.environ.get("MYSQL_DATABASE", "")
    if args.action != "upgrade" and (
        os.environ.get("CAMPUSCLAW_ISOLATED_DATABASE") != "1"
        or not database.startswith("campusclaw_test_")
    ):
        parser.error("该命令仅允许用于明确登记的隔离测试库")
    if (args.action == "replay-deletions") != (args.manifest is not None):
        parser.error("重放命令必须通过 --manifest 指定删除清单")
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
            elif args.action == "export-deletions":
                rows = MaterialRepository(engine).deletion_manifest()
                print(
                    json.dumps(
                        [
                            {
                                "material_id": row["material_id"],
                                "deleted_at": row["deleted_at"]
                                .replace(tzinfo=UTC)
                                .isoformat(),
                            }
                            for row in rows
                        ]
                    )
                )
            elif args.action == "replay-deletions":
                MaterialRepository(engine).replay_deletions(
                    _read_manifest(args.manifest)
                )
            else:
                migrate(engine, downgrade=args.action == "downgrade")
        finally:
            engine.dispose()
    except (KeyError, ValueError, OSError, DatabaseError):
        parser.exit(1, "认证数据库命令失败，请核对隔离配置、库权限和迁移状态。\n")


if __name__ == "__main__":
    main()
