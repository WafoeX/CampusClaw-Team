"""本人会话与逻辑轮次的短事务存储；网络与模型调用由服务层在事务外执行。"""

from sqlalchemy import delete, exists, func, insert, select, update

from app.adapters.assistant_schema_v8 import (
    citations,
    feedback,
    messages,
    operations,
    runs,
    sessions,
)
from app.adapters.chapter_schema_v4 import chapters
from app.adapters.index_schema_v5 import materials
from app.adapters.material_schema_v2 import deletions


class SessionRepositoryMixin:
    @staticmethod
    def session_scope(identity):
        return (
            sessions.c.class_id == identity.class_id,
            sessions.c.owner_id == identity.subject_id,
        )

    def lock_session(self, connection, identity, session_id):
        return (
            connection.execute(
                select(sessions)
                .where(*self.session_scope(identity), sessions.c.id == session_id)
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )

    def insert_session(self, connection, values):
        connection.execute(insert(sessions).values(values))

    def list_sessions(self, connection, identity, now, page, size):
        query = select(sessions).where(
            *self.session_scope(identity), sessions.c.expires_at > now
        )
        total = connection.scalar(select(func.count()).select_from(query.subquery()))
        rows = (
            connection.execute(
                query.order_by(sessions.c.updated_at.desc(), sessions.c.id.desc())
                .limit(size)
                .offset((page - 1) * size)
            )
            .mappings()
            .all()
        )
        return rows, total

    @staticmethod
    def chapter_accessible(connection, class_id, chapter_id):
        return (
            connection.scalar(
                select(chapters.c.id).where(
                    chapters.c.class_id == class_id, chapters.c.id == chapter_id
                )
            )
            is not None
        )

    @staticmethod
    def operation_scope(identity, session_id):
        return (
            operations.c.class_id == identity.class_id,
            operations.c.owner_id == identity.subject_id,
            operations.c.session_id == session_id,
        )

    def lock_session_operation(
        self, connection, identity, session_id, *, key=None, operation_id=None
    ):
        conditions = list(self.operation_scope(identity, session_id))
        if key is not None:
            conditions.append(operations.c.request_key == key)
        if operation_id is not None:
            conditions.append(operations.c.id == operation_id)
        return (
            connection.execute(select(operations).where(*conditions).with_for_update())
            .mappings()
            .one_or_none()
        )

    def active_session_operations(self, connection, identity, session_id):
        return (
            connection.execute(
                select(operations)
                .where(
                    *self.operation_scope(identity, session_id),
                    operations.c.status == "running",
                )
                .with_for_update()
            )
            .mappings()
            .all()
        )

    @staticmethod
    def insert_user_message(connection, operation, question, message_id):
        connection.execute(
            insert(messages).values(
                id=message_id,
                class_id=operation["class_id"],
                owner_id=operation["owner_id"],
                session_id=operation["session_id"],
                operation_id=operation["id"],
                role="user",
                content=question,
                content_state="available",
                created_at=operation["created_at"],
                expires_at=operation["expires_at"],
            )
        )

    @staticmethod
    def session_messages(connection, identity, session_id, now, page=1, size=20):
        query = select(messages).where(
            messages.c.class_id == identity.class_id,
            messages.c.owner_id == identity.subject_id,
            messages.c.session_id == session_id,
            messages.c.expires_at > now,
        )
        total = connection.scalar(select(func.count()).select_from(query.subquery()))
        rows = (
            connection.execute(
                query.order_by(messages.c.created_at, messages.c.id)
                .limit(size)
                .offset((page - 1) * size)
            )
            .mappings()
            .all()
        )
        return rows, total

    @staticmethod
    def history(connection, identity, session_id, now):
        return (
            connection.execute(
                select(messages)
                .join(operations, operations.c.id == messages.c.operation_id)
                .where(
                    messages.c.class_id == identity.class_id,
                    messages.c.owner_id == identity.subject_id,
                    messages.c.session_id == session_id,
                    messages.c.expires_at > now,
                    messages.c.content_state == "available",
                    operations.c.status == "succeeded",
                )
                .order_by(messages.c.created_at.desc(), messages.c.id.desc())
                .limit(6)
            )
            .mappings()
            .all()
        )

    @staticmethod
    def message_sources(connection, identity, message_id):
        rows = (
            connection.execute(
                select(
                    citations,
                    materials.c.id.label("current_material_id"),
                    materials.c.content_version.label("current_source_version"),
                    materials.c.active_index_version.label("current_index_version"),
                )
                .select_from(citations)
                .outerjoin(
                    materials,
                    (materials.c.id == citations.c.material_id)
                    & (materials.c.class_id == citations.c.class_id)
                    & ~exists(
                        select(deletions.c.material_id).where(
                            deletions.c.material_id == citations.c.material_id
                        )
                    ),
                )
                .where(
                    citations.c.class_id == identity.class_id,
                    citations.c.owner_id == identity.subject_id,
                    citations.c.message_id == message_id,
                )
                .order_by(citations.c.ordinal)
            )
            .mappings()
            .all()
        )
        return rows

    @staticmethod
    def lock_evidence(connection, class_id, evidence):
        # 和原文删除共用资料锁；阻止校验后、提交前来源被删除或改版。
        from app.adapters.index_schema_v5 import materials as indexed_materials

        for item in sorted(evidence, key=lambda value: value["material_id"]):
            row = (
                connection.execute(
                    select(indexed_materials)
                    .where(
                        indexed_materials.c.class_id == class_id,
                        indexed_materials.c.id == item["material_id"],
                    )
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if (
                row is None
                or row["content_version"] != item["source_version"]
                or row["active_index_version"] != item["index_version"]
            ):
                return False
        return True

    @staticmethod
    def completed_message(connection, operation_id):
        return (
            connection.execute(
                select(messages).where(
                    messages.c.operation_id == operation_id,
                    messages.c.role == "assistant",
                )
            )
            .mappings()
            .one_or_none()
        )

    @staticmethod
    def commit_message(connection, identity, ticket, text, cited, now):
        values = dict(
            class_id=identity.class_id,
            owner_id=identity.subject_id,
            session_id=ticket["session_id"],
            expires_at=ticket["expires_at"],
            created_at=now,
        )
        connection.execute(
            insert(messages).values(
                values
                | dict(
                    id=ticket["message_id"],
                    operation_id=ticket["operation_id"],
                    role="assistant",
                    content=text,
                    content_state="available",
                )
            )
        )
        for number in cited:
            item = ticket["evidence"][number - 1]
            connection.execute(
                insert(citations).values(
                    values
                    | dict(
                        message_id=ticket["message_id"],
                        ordinal=number,
                        material_id=item["material_id"],
                        source_version=item["source_version"],
                        index_version=item["index_version"],
                        index_config_version=item["index_config_version"],
                        start_offset=item["start"],
                        end_offset=item["end"],
                        title=item["title"],
                        excerpt=item["text"],
                        status="available",
                    )
                )
            )
        connection.execute(
            update(sessions)
            .where(
                sessions.c.class_id == identity.class_id,
                sessions.c.owner_id == identity.subject_id,
                sessions.c.id == ticket["session_id"],
            )
            .values(updated_at=now)
        )

    def cleanup_sessions(self, connection, now):
        ids = list(
            connection.scalars(
                select(sessions.c.id)
                .where(sessions.c.expires_at <= now)
                .order_by(sessions.c.expires_at, sessions.c.id)
                .limit(100)
                .with_for_update()
            )
        )
        if ids:
            # 先解除所有私有子对象；备份恢复依旧必须按原expires_at重放。
            for table in (feedback, citations, messages, runs):
                if table is runs:
                    operation_ids = select(operations.c.id).where(
                        operations.c.session_id.in_(ids)
                    )
                    connection.execute(
                        delete(runs).where(runs.c.operation_id.in_(operation_ids))
                    )
                else:
                    connection.execute(delete(table).where(table.c.session_id.in_(ids)))
            connection.execute(
                delete(operations).where(operations.c.session_id.in_(ids))
            )
            connection.execute(delete(sessions).where(sessions.c.id.in_(ids)))
        return len(ids)
