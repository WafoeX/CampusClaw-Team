"""允许保存内置错题讲解技能；不回填既有技能。"""

from alembic import op
from sqlalchemy import text

revision = "0018_mistake_explanation_skill"
down_revision = "0017_teacher_score_override"

CONSTRAINT = "ck_skills_builtin"
OLD_RULE = "builtin_key IS NULL OR builtin_key IN ('problem_guidance','learning_plan')"
NEW_RULE = (
    "builtin_key IS NULL OR builtin_key IN "
    "('problem_guidance','learning_plan','mistake_explanation')"
)


def replace(rule):
    op.drop_constraint(CONSTRAINT, "skills", type_="check")
    op.create_check_constraint(CONSTRAINT, "skills", rule)


def upgrade():
    replace(NEW_RULE)


def downgrade():
    connection = op.get_bind()
    if not connection.engine.url.database.startswith("campusclaw_test_"):
        raise ValueError("只允许在合成隔离库物理降级错题讲解技能约束")
    count = connection.scalar(
        text("SELECT COUNT(*) FROM skills WHERE builtin_key='mistake_explanation'")
    )
    if count:
        raise ValueError("降级前须删除合成库中的错题讲解技能")
    replace(OLD_RULE)
