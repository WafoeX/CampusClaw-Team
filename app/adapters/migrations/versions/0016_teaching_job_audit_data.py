"""扩展候选任务用量与班级操作审计查询，不回填旧记录。"""

from alembic import op
from sqlalchemy import inspect

revision = "0016_teaching_job_audit_data"
down_revision = "0015_quiz_list_index"

JOB_CHECK = "ck_teaching_job_usage"
AUDIT_CHECK = "ck_operation_audit_outcome"
AUDIT_INDEX = "ix_operation_audit_class_resource"


def _names(connection, table, key):
    inspector = inspect(connection)
    return {item["name"] for item in getattr(inspector, key)(table)}


def upgrade():
    connection = op.get_bind()
    columns = _names(connection, "teaching_jobs", "get_columns")
    if "total_tokens" not in columns:
        connection.exec_driver_sql(
            "ALTER TABLE teaching_jobs ADD COLUMN total_tokens INT NULL"
        )
    if "usage_status" not in columns:
        connection.exec_driver_sql(
            "ALTER TABLE teaching_jobs ADD COLUMN usage_status VARCHAR(16) NULL"
        )
    if JOB_CHECK not in _names(connection, "teaching_jobs", "get_check_constraints"):
        connection.exec_driver_sql(
            "ALTER TABLE teaching_jobs ADD CONSTRAINT ck_teaching_job_usage CHECK ("
            "(usage_status IS NULL AND total_tokens IS NULL) OR "
            "(usage_status = 'measured' AND total_tokens IS NOT NULL AND total_tokens >= 0) OR "
            "(usage_status IN ('not_applicable','unavailable') AND total_tokens IS NULL))"
        )

    checks = {
        item["name"]: item["sqltext"]
        for item in inspect(connection).get_check_constraints("operation_audit_events")
    }
    if "dead_letter" not in checks.get(AUDIT_CHECK, ""):
        if AUDIT_CHECK in checks:
            connection.exec_driver_sql(
                "ALTER TABLE operation_audit_events DROP CHECK ck_operation_audit_outcome"
            )
        connection.exec_driver_sql(
            "ALTER TABLE operation_audit_events ADD CONSTRAINT ck_operation_audit_outcome "
            "CHECK (outcome IN ('succeeded','denied','failed','cancelled','dead_letter'))"
        )
    if AUDIT_INDEX not in _names(connection, "operation_audit_events", "get_indexes"):
        connection.exec_driver_sql(
            "CREATE INDEX ix_operation_audit_class_resource ON operation_audit_events "
            "(class_id, resource_type, resource_id, created_at, id)"
        )


def downgrade():
    connection = op.get_bind()
    if not connection.engine.url.database.startswith("campusclaw_test_"):
        raise ValueError("只允许在合成隔离库物理降级候选任务审计扩展")
    if AUDIT_INDEX in _names(connection, "operation_audit_events", "get_indexes"):
        op.drop_index(AUDIT_INDEX, table_name="operation_audit_events")
    checks = _names(connection, "operation_audit_events", "get_check_constraints")
    if AUDIT_CHECK in checks:
        connection.exec_driver_sql(
            "ALTER TABLE operation_audit_events DROP CHECK ck_operation_audit_outcome"
        )
    connection.exec_driver_sql(
        "ALTER TABLE operation_audit_events ADD CONSTRAINT ck_operation_audit_outcome "
        "CHECK (outcome IN ('succeeded','denied'))"
    )
    if JOB_CHECK in _names(connection, "teaching_jobs", "get_check_constraints"):
        connection.exec_driver_sql(
            "ALTER TABLE teaching_jobs DROP CHECK ck_teaching_job_usage"
        )
    columns = _names(connection, "teaching_jobs", "get_columns")
    if "usage_status" in columns:
        op.drop_column("teaching_jobs", "usage_status")
    if "total_tokens" in columns:
        op.drop_column("teaching_jobs", "total_tokens")
