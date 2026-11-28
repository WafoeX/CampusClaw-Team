"""一次性 MySQL：验证 0019 空库、重复升级、旧结构兼容和隔离降级。"""

import os
from pathlib import Path

from alembic import command
from sqlalchemy import inspect

from app.adapters.database import mysql_engine
from app.adapters.migrations.runner import migrate, migration_config
from app.config import Settings

settings = Settings.load(os.environ, Path("app/BUILD_VERSION"))
engine = mysql_engine(
    host=settings.mysql_host,
    port=settings.mysql_port,
    database=settings.mysql_database,
    user=settings.mysql_user,
    password=settings.mysql_password,
)
assert engine.url.database.startswith("campusclaw_test_")
migrate(engine)
migrate(engine)
tables = set(inspect(engine).get_table_names())
assert "quiz_submission_jobs" in tables
assert {"quiz_submissions", "quiz_results", "quiz_score_overrides"} <= tables
columns = {
    item["name"]: item for item in inspect(engine).get_columns("quiz_submission_jobs")
}
assert columns["answers"]["nullable"] is True
assert columns["submission_id"]["nullable"] is False
assert {
    "uq_submission_jobs_submission",
    "uq_submission_jobs_student_quiz",
} <= {
    item["name"]
    for item in inspect(engine).get_unique_constraints("quiz_submission_jobs")
}

config = migration_config()
with engine.connect() as connection:
    config.attributes["connection"] = connection
    command.downgrade(config, "0018_mistake_explanation_skill")
    connection.commit()
tables = set(inspect(engine).get_table_names())
assert "quiz_submission_jobs" not in tables
assert {"quiz_submissions", "quiz_results", "quiz_score_overrides"} <= tables

migrate(engine)
migrate(engine)
assert "quiz_submission_jobs" in inspect(engine).get_table_names()
print("submission_job_migration_ok")
