"""班级配置与本人同步执行的数据访问；网络调用不在仓储事务中。"""

from sqlalchemy import delete, exists, func, insert, or_, select, text, update

from app.adapters.assistant_schema_v8 import (
    assistant_materials,
    assistant_revisions,
    assistant_skills,
    assistants,
    audits,
    operations,
    runs,
    sessions,
    skills,
    template_revisions,
)
from app.adapters.assistant_schema_v9 import config_requests, templates
from app.adapters.feedback_repository import FeedbackRepositoryMixin
from app.adapters.material_repository import MaterialRepository
from app.adapters.material_schema_v2 import materials
from app.adapters.session_repository import SessionRepositoryMixin
from app.adapters.skill_repository import SkillRepositoryMixin

CONFIGS = {
    "template": (templates, template_revisions, "template_id"),
    "assistant": (assistants, assistant_revisions, "assistant_id"),
}


class AIRepository(
    FeedbackRepositoryMixin,
    SessionRepositoryMixin,
    SkillRepositoryMixin,
    MaterialRepository,
):
    @staticmethod
    def _config_scope(kind, class_id):
        table = CONFIGS[kind][0]
        clauses = [table.c.class_id == class_id]
        if kind == "template":
            clauses.append(table.c.deleted.is_(False))
        return clauses

    def bindable_skills(self, class_id):
        with self.engine.connect() as connection:
            return (
                connection.execute(
                    select(skills.c.id, skills.c.name)
                    .where(skills.c.class_id == class_id, skills.c.enabled.is_(True))
                    .order_by(skills.c.name, skills.c.id)
                    .limit(100)
                )
                .mappings()
                .all()
            )

    def configurations(
        self, kind, class_id, page, page_size, *, teacher=False, app_key=None
    ):
        table = CONFIGS[kind][0]
        clauses = self._config_scope(kind, class_id)
        if app_key is not None:
            clauses.append(table.c.app_key == app_key)
        if not teacher:
            clauses.append(table.c.enabled.is_(True))
        with self.engine.connect() as connection:
            total = connection.scalar(
                select(func.count()).select_from(table).where(*clauses)
            )
            rows = (
                connection.execute(
                    select(table)
                    .where(*clauses)
                    .order_by(table.c.updated_at.desc(), table.c.id.desc())
                    .limit(page_size)
                    .offset((page - 1) * page_size)
                )
                .mappings()
                .all()
            )
        return rows, total

    def lock_configuration(self, connection, kind, class_id, resource_id):
        table, revisions, key = CONFIGS[kind]
        row = (
            connection.execute(
                select(table)
                .where(*self._config_scope(kind, class_id), table.c.id == resource_id)
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        version = (
            connection.execute(
                select(revisions).where(
                    revisions.c.class_id == class_id,
                    revisions.c[key] == resource_id,
                    revisions.c.revision == row["revision"],
                )
            )
            .mappings()
            .one()
        )
        result = dict(row) | {"prompt": version["prompt"]}
        if kind == "assistant":
            for binding, output, column in (
                (assistant_materials, "material_ids", "material_id"),
                (assistant_skills, "skill_ids", "skill_id"),
            ):
                result[output] = list(
                    connection.scalars(
                        select(binding.c[column])
                        .where(
                            binding.c.class_id == class_id,
                            binding.c.assistant_id == resource_id,
                            binding.c.revision == row["revision"],
                        )
                        .order_by(binding.c[column])
                    )
                )
        return result

    def bindings_exist(self, connection, class_id, material_ids, skill_ids):
        for table, ids in ((materials, material_ids), (skills, skill_ids)):
            if ids:
                found = set(
                    connection.scalars(
                        select(table.c.id)
                        .where(table.c.class_id == class_id, table.c.id.in_(ids))
                        .order_by(table.c.id)
                        .with_for_update()
                    )
                )
                if found != set(ids):
                    return False
        return True

    def store_configuration(
        self,
        connection,
        kind,
        parent,
        prompt,
        actor_id,
        *,
        new=False,
        material_ids=(),
        skill_ids=(),
        event="update",
    ):
        table, revisions, key = CONFIGS[kind]
        if new:
            connection.execute(insert(table).values(parent))
        else:
            connection.execute(
                update(table)
                .where(table.c.id == parent["id"])
                .values({k: v for k, v in parent.items() if k != "id"})
            )
        connection.execute(
            insert(revisions).values(
                class_id=parent["class_id"],
                **{key: parent["id"]},
                revision=parent["revision"],
                creator_id=actor_id,
                prompt=prompt,
                created_at=parent["updated_at"],
            )
        )
        if kind == "assistant":
            for binding, ids, column in (
                (assistant_materials, material_ids, "material_id"),
                (assistant_skills, skill_ids, "skill_id"),
            ):
                if ids:
                    connection.execute(
                        insert(binding),
                        [
                            dict(
                                class_id=parent["class_id"],
                                assistant_id=parent["id"],
                                revision=parent["revision"],
                                **{column: identifier},
                            )
                            for identifier in ids
                        ],
                    )
        from uuid import uuid4

        connection.execute(
            insert(audits).values(
                id=str(uuid4()),
                class_id=parent["class_id"],
                actor_id=actor_id,
                resource_type=kind,
                resource_id=parent["id"],
                revision=parent["revision"],
                event=event,
                created_at=parent["updated_at"],
            )
        )

    def lock_creation(self, connection, class_id, actor_id, kind, key):
        return (
            connection.execute(
                select(config_requests)
                .where(
                    config_requests.c.class_id == class_id,
                    config_requests.c.actor_id == actor_id,
                    config_requests.c.resource_type == kind,
                    config_requests.c.request_key == key,
                )
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )

    def discard_creation(self, connection, class_id, actor_id, kind, key):
        connection.execute(
            delete(config_requests).where(
                config_requests.c.class_id == class_id,
                config_requests.c.actor_id == actor_id,
                config_requests.c.resource_type == kind,
                config_requests.c.request_key == key,
            )
        )

    def current_attempt(self, connection, operation_id, attempt):
        return (
            connection.execute(
                select(runs).where(
                    runs.c.operation_id == operation_id, runs.c.attempt == attempt
                )
            )
            .mappings()
            .one()
        )

    def save_creation(self, connection, values, now):
        connection.execute(
            text(
                "DELETE FROM ai_configuration_requests WHERE expires_at <= :now LIMIT 100"
            ),
            {"now": now},
        )
        connection.execute(insert(config_requests).values(values))

    def lock_operation(self, connection, identity, app_key, key):
        return (
            connection.execute(
                select(operations)
                .where(
                    operations.c.class_id == identity.class_id,
                    operations.c.owner_id == identity.subject_id,
                    operations.c.operation_scope == app_key.encode(),
                    operations.c.request_key == key,
                )
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )

    def insert_attempt(self, connection, operation, run, *, new):
        if new:
            connection.execute(insert(operations).values(operation))
        else:
            connection.execute(
                update(operations)
                .where(operations.c.id == operation["id"])
                .values(operation)
            )
        connection.execute(insert(runs).values(run))

    def finish_attempt(
        self,
        connection,
        ticket,
        *,
        status,
        error_code=None,
        details=None,
        duration_ms=0,
        now,
    ):
        connection.execute(
            update(runs)
            .where(runs.c.id == ticket["run_id"], runs.c.status == "running")
            .values(
                status=status,
                details=details,
                error_code=error_code,
                duration_ms=duration_ms,
                updated_at=now,
            )
        )
        values = dict(
            status=status, lease_token=None, lease_expires_at=None, updated_at=now
        )
        if status != "succeeded":
            values["input_payload"] = None
        connection.execute(
            update(operations)
            .where(operations.c.id == ticket["operation_id"])
            .values(values)
        )

    def lock_ticket(self, connection, identity, ticket):
        return (
            connection.execute(
                select(operations)
                .where(
                    operations.c.id == ticket["operation_id"],
                    operations.c.class_id == identity.class_id,
                    operations.c.owner_id == identity.subject_id,
                    operations.c.session_id.is_(None),
                )
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )

    def operation_result(self, connection, identity, operation_id, now):
        return (
            connection.execute(
                self._runs_query(identity, now).where(
                    operations.c.id == operation_id, runs.c.status == "succeeded"
                )
            )
            .mappings()
            .one_or_none()
        )

    @staticmethod
    def _runs_query(identity, now):
        return (
            select(
                runs,
                operations.c.app_key,
                operations.c.session_id,
                operations.c.input_payload,
                operations.c.lease_expires_at,
            )
            .join(operations, operations.c.id == runs.c.operation_id)
            .where(
                operations.c.class_id == identity.class_id,
                operations.c.owner_id == identity.subject_id,
                runs.c.class_id == identity.class_id,
                runs.c.owner_id == identity.subject_id,
                or_(
                    operations.c.session_id.is_(None),
                    exists(
                        select(sessions.c.id).where(
                            sessions.c.id == operations.c.session_id,
                            sessions.c.class_id == identity.class_id,
                            sessions.c.owner_id == identity.subject_id,
                            sessions.c.expires_at > now,
                        )
                    ),
                ),
                operations.c.expires_at > now,
                runs.c.expires_at > now,
            )
        )

    def _safe_run(self, connection, identity, row, now):
        if row is None or row["session_id"] is None:
            return row
        message = self.completed_message(connection, row["operation_id"])
        if message is not None:
            refs = self.message_sources(connection, identity, message["id"])
            if message["content_state"] != "available" or any(
                ref["status"] != "available"
                or ref["current_material_id"] is None
                or ref["expires_at"] <= now
                for ref in refs
            ):
                return dict(row) | {
                    "status": "revoked",
                    "details": None,
                    "input_payload": None,
                }
        return row

    def read_run(self, identity, run_id, now):
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    self._runs_query(identity, now).where(runs.c.id == run_id)
                )
                .mappings()
                .one_or_none()
            )
            return self._safe_run(connection, identity, row, now)

    def list_runs(self, identity, page, page_size, now):
        query = self._runs_query(identity, now)
        with self.engine.connect() as connection:
            total = connection.scalar(
                select(func.count()).select_from(query.subquery())
            )
            rows = (
                connection.execute(
                    query.order_by(runs.c.updated_at.desc(), runs.c.id.desc())
                    .limit(page_size)
                    .offset((page - 1) * page_size)
                )
                .mappings()
                .all()
            )
            return [
                self._safe_run(connection, identity, row, now) for row in rows
            ], total

    def cleanup_expired(self, now):
        with self.engine.begin() as connection:
            ids = list(
                connection.scalars(
                    select(operations.c.id)
                    .where(
                        operations.c.session_id.is_(None),
                        operations.c.expires_at <= now,
                    )
                    .order_by(operations.c.expires_at, operations.c.id)
                    .limit(100)
                    .with_for_update()
                )
            )
            if ids:
                connection.execute(delete(runs).where(runs.c.operation_id.in_(ids)))
                connection.execute(delete(operations).where(operations.c.id.in_(ids)))
            session_count = self.cleanup_sessions(connection, now)
            result = connection.execute(
                text(
                    "DELETE FROM ai_configuration_requests WHERE expires_at <= :now LIMIT 100"
                ),
                {"now": now},
            )
        return {
            "operations": len(ids),
            "sessions": session_count,
            "configuration_requests": result.rowcount,
        }
