"""历史消息与反馈访问；教师查询投影只在服务层公开最小字段。"""

from sqlalchemy import exists, func, insert, or_, select, update

from app.adapters.assistant_schema_v8 import (
    audits,
    citations,
    feedback,
    messages,
    operations,
    sessions,
)
from app.adapters.chapter_schema_v4 import chapters
from app.adapters.material_schema_v2 import deletions, materials


def unavailable_sources(message_id, now):
    return exists(
        select(citations.c.message_id).where(
            citations.c.message_id == message_id,
            or_(
                citations.c.status != "available",
                citations.c.expires_at <= now,
                ~exists(
                    select(materials.c.id).where(
                        materials.c.id == citations.c.material_id,
                        materials.c.class_id == citations.c.class_id,
                    )
                ),
                exists(
                    select(deletions.c.material_id).where(
                        deletions.c.material_id == citations.c.material_id
                    )
                ),
            ),
        )
    )


class FeedbackRepositoryMixin:
    @staticmethod
    def lock_message(connection, identity, session_id, message_id, now):
        return (
            connection.execute(
                select(messages)
                .where(
                    messages.c.class_id == identity.class_id,
                    messages.c.owner_id == identity.subject_id,
                    messages.c.session_id == session_id,
                    messages.c.id == message_id,
                    messages.c.expires_at > now,
                )
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )

    @staticmethod
    def message_feedback(connection, message_id):
        return (
            connection.execute(
                select(feedback)
                .where(feedback.c.message_id == message_id)
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )

    @staticmethod
    def save_feedback(connection, values, *, new):
        if new:
            connection.execute(insert(feedback).values(values))
        else:
            connection.execute(
                update(feedback).where(feedback.c.id == values["id"]).values(values)
            )

    @staticmethod
    def feedback_audit(connection, identity, row, event):
        from uuid import uuid4

        connection.execute(
            insert(audits).values(
                id=str(uuid4()),
                class_id=identity.class_id,
                actor_id=identity.subject_id,
                resource_type="feedback",
                resource_id=row["id"],
                revision=row["revision"],
                event=event,
                created_at=row["updated_at"],
            )
        )

    @staticmethod
    def feedback_query(class_id, now):
        return (
            select(feedback, chapters.c.name.label("chapter_name"))
            .select_from(feedback)
            .join(
                sessions,
                (sessions.c.id == feedback.c.session_id)
                & (sessions.c.class_id == feedback.c.class_id)
                & (sessions.c.owner_id == feedback.c.owner_id),
            )
            .join(messages, messages.c.id == feedback.c.message_id)
            .outerjoin(
                chapters,
                (chapters.c.id == feedback.c.chapter_id)
                & (chapters.c.class_id == class_id),
            )
            .where(
                feedback.c.class_id == class_id,
                feedback.c.expires_at > now,
                sessions.c.expires_at > now,
                messages.c.expires_at > now,
                messages.c.role == "assistant",
                messages.c.content_state == "available",
                feedback.c.status != "unavailable",
                ~unavailable_sources(messages.c.id, now),
            )
        )

    def teaching_feedback(self, connection, class_id, now, status, page, size):
        query = self.feedback_query(class_id, now).where(
            feedback.c.rating == "unresolved", feedback.c.status == status
        )
        total = connection.scalar(select(func.count()).select_from(query.subquery()))
        rows = (
            connection.execute(
                query.order_by(feedback.c.updated_at.desc(), feedback.c.id.desc())
                .limit(size)
                .offset((page - 1) * size)
            )
            .mappings()
            .all()
        )
        return rows, total

    def lock_teaching_feedback(self, connection, class_id, now, feedback_id):
        return (
            connection.execute(
                self.feedback_query(class_id, now)
                .where(feedback.c.id == feedback_id)
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )

    @staticmethod
    def feedback_chapter(connection, operation_id, class_id):
        payload = (
            connection.scalar(
                select(operations.c.input_payload).where(
                    operations.c.id == operation_id
                )
            )
            or {}
        )
        chapter_id = payload.get("chapter_scope")
        if chapter_id is None or chapter_id == "uncategorized":
            return None
        return connection.scalar(
            select(chapters.c.name).where(
                chapters.c.class_id == class_id, chapters.c.id == chapter_id
            )
        )

    @staticmethod
    def feedback_operation(connection, operation_id):
        return (
            connection.execute(
                select(operations).where(operations.c.id == operation_id)
            )
            .mappings()
            .one()
        )
