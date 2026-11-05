from hashlib import sha256
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.util import CommandError
from sqlalchemy import func, select


def migrate(engine, *, downgrade=False):
    database = engine.url.database
    if downgrade and not database.startswith("campusclaw_test_"):
        raise ValueError("只允许在隔离测试库执行数据库降级")
    lock_name = sha256(f"campusclaw-migrations:{database}".encode()).hexdigest()
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent))
    with engine.connect() as connection:
        acquired = connection.scalar(select(func.get_lock(lock_name, 4)))
        if acquired != 1:
            raise ValueError("认证数据库已有迁移在执行")
        connection.commit()
        try:
            config.attributes["connection"] = connection
            if downgrade:
                command.downgrade(config, "base")
            else:
                command.upgrade(config, "head")
        except CommandError:
            raise ValueError("认证数据库迁移版本不匹配") from None
        finally:
            connection.rollback()
            connection.scalar(select(func.release_lock(lock_name)))
