"""复用0008技能存储；班级锁保护名称，修订与审计同事务。"""

from uuid import uuid4

from sqlalchemy import delete, func, insert, select, update

from app.adapters.assistant_schema_v8 import (
    assistant_skills,
    assistants,
    audits,
    skill_revisions,
    skills,
)
from app.adapters.auth_schema_v1 import classes


class SkillRepositoryMixin:
    def lock_skill_class(self, connection, class_id):
        connection.execute(
            select(classes.c.id).where(classes.c.id == class_id).with_for_update()
        ).one()

    def lock_skill(self, connection, class_id, resource_id):
        row = (
            connection.execute(
                select(skills)
                .where(skills.c.class_id == class_id, skills.c.id == resource_id)
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        return self._skill_definition(connection, row) if row else None

    @staticmethod
    def _skill_definition(connection, row):
        payload = connection.scalar(
            select(skill_revisions.c.definition).where(
                skill_revisions.c.class_id == row["class_id"],
                skill_revisions.c.skill_id == row["id"],
                skill_revisions.c.revision == row["revision"],
            )
        )
        return dict(row) | {"definition": payload}

    def list_skills(self, connection, class_id, page, size):
        scope = skills.c.class_id == class_id
        total = connection.scalar(select(func.count()).select_from(skills).where(scope))
        rows = (
            connection.execute(
                select(skills)
                .where(scope)
                .order_by(skills.c.updated_at.desc(), skills.c.id.desc())
                .limit(size)
                .offset((page - 1) * size)
            )
            .mappings()
            .all()
        )
        return [self._skill_definition(connection, row) for row in rows], total

    def bound_skills(self, connection, class_id, assistant_id, revision):
        rows = (
            connection.execute(
                select(skills)
                .join(
                    assistant_skills,
                    (assistant_skills.c.class_id == skills.c.class_id)
                    & (assistant_skills.c.skill_id == skills.c.id),
                )
                .join(
                    assistants,
                    (assistants.c.class_id == assistant_skills.c.class_id)
                    & (assistants.c.id == assistant_skills.c.assistant_id),
                )
                .where(
                    skills.c.class_id == class_id,
                    skills.c.enabled.is_(True),
                    assistants.c.enabled.is_(True),
                    assistants.c.revision == revision,
                    assistant_skills.c.assistant_id == assistant_id,
                    assistant_skills.c.revision == revision,
                )
                .order_by(skills.c.id)
                .with_for_update()
            )
            .mappings()
            .all()
        )
        return [self._skill_definition(connection, row) for row in rows]

    @staticmethod
    def skill_name_exists(connection, class_id, name_key, resource_id):
        return (
            connection.scalar(
                select(skills.c.id).where(
                    skills.c.class_id == class_id,
                    skills.c.name_key == name_key,
                    skills.c.id != (resource_id or ""),
                )
            )
            is not None
        )

    def store_skill(self, connection, parent, definition, actor_id, *, new):
        if new:
            connection.execute(insert(skills).values(parent))
        else:
            connection.execute(
                update(skills)
                .where(
                    skills.c.class_id == parent["class_id"], skills.c.id == parent["id"]
                )
                .values(parent)
            )
        connection.execute(
            insert(skill_revisions).values(
                class_id=parent["class_id"],
                skill_id=parent["id"],
                revision=parent["revision"],
                creator_id=actor_id,
                definition=definition,
                created_at=parent["updated_at"],
            )
        )
        self._skill_audit(
            connection,
            parent,
            actor_id,
            "create" if new else "update",
            parent["updated_at"],
        )

    @staticmethod
    def _skill_audit(connection, row, actor_id, event, now):
        connection.execute(
            insert(audits).values(
                id=str(uuid4()),
                class_id=row["class_id"],
                actor_id=actor_id,
                resource_type="skill",
                resource_id=row["id"],
                revision=row["revision"],
                event=event,
                created_at=now,
            )
        )

    def delete_skill(self, connection, row, actor_id, now):
        self._skill_audit(connection, row, actor_id, "delete", now)
        connection.execute(
            delete(skills).where(
                skills.c.class_id == row["class_id"], skills.c.id == row["id"]
            )
        )
