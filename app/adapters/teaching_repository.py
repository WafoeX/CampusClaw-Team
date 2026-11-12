"""教学闭环的 MySQL 访问；所有正式写入由调用方事务包裹。"""

from sqlalchemy import func, insert, select, text, update

from app.adapters.auth_schema_v1 import accounts
from app.adapters.chapter_schema_v4 import chapters, materials
from app.adapters.feedback_repository import FeedbackRepositoryMixin
from app.adapters.index_schema_v5 import materials as indexed_materials
from app.adapters.material_repository import MaterialRepository
from app.adapters.teaching_schema_v10 import (
    question_audits,
    question_versions,
    questions,
    quiz_audits,
    quiz_draft_items,
    quiz_drafts,
    quiz_items,
    quiz_participants,
    quiz_results,
    quiz_submissions,
    quizzes,
)
from app.adapters.teaching_schema_v12 import generated_questions, question_sources


class TeachingRepository(MaterialRepository):
    def now(self, connection):
        return connection.scalar(text("SELECT UTC_TIMESTAMP(6)"))

    def question(self, connection, class_id, question_id, *, lock=False):
        statement = (
            select(questions, generated_questions.c.job_id)
            .outerjoin(
                generated_questions, generated_questions.c.question_id == questions.c.id
            )
            .where(questions.c.class_id == class_id, questions.c.id == question_id)
        )
        if lock:
            statement = statement.with_for_update()
        return connection.execute(statement).mappings().one_or_none()

    def version(self, connection, class_id, question_id, version):
        return (
            connection.execute(
                select(question_versions).where(
                    question_versions.c.class_id == class_id,
                    question_versions.c.question_id == question_id,
                    question_versions.c.version == version,
                )
            )
            .mappings()
            .one_or_none()
        )

    def list_questions(self, class_id, page, page_size):
        with self.engine.connect() as connection:
            scope = questions.c.class_id == class_id
            total = connection.scalar(
                select(func.count()).select_from(questions).where(scope)
            )
            rows = (
                connection.execute(
                    select(
                        questions,
                        question_versions.c.kind,
                        question_versions.c.stem,
                        generated_questions.c.job_id,
                    )
                    .join(
                        question_versions,
                        (question_versions.c.question_id == questions.c.id)
                        & (question_versions.c.version == questions.c.current_version),
                    )
                    .outerjoin(
                        generated_questions,
                        generated_questions.c.question_id == questions.c.id,
                    )
                    .where(scope)
                    .order_by(questions.c.created_at.desc(), questions.c.id)
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
                .mappings()
                .all()
            )
        return rows, total

    def material_exists(self, connection, class_id, material_id):
        return (
            connection.scalar(
                select(materials.c.id).where(
                    materials.c.class_id == class_id,
                    materials.c.id == material_id,
                )
            )
            is not None
        )

    def source_material(self, connection, class_id, material_id, *, lock=False):
        statement = select(indexed_materials).where(
            indexed_materials.c.class_id == class_id,
            indexed_materials.c.id == material_id,
        )
        if lock:
            statement = statement.with_for_update()
        return connection.execute(statement).mappings().one_or_none()

    def save_source(self, connection, version, snapshot):
        connection.execute(
            insert(question_sources).values(
                question_id=version["question_id"],
                version=version["version"],
                class_id=version["class_id"],
                material_id=version["source_material_id"],
                snapshot=snapshot,
            )
        )

    def source_snapshot(self, connection, class_id, question_id, version, material_id):
        if material_id is None:
            return None
        return connection.scalar(
            select(question_sources.c.snapshot).where(
                question_sources.c.class_id == class_id,
                question_sources.c.question_id == question_id,
                question_sources.c.version == version,
                question_sources.c.material_id == material_id,
            )
        )

    def chapter_exists(self, connection, class_id, chapter_id, *, lock=False):
        statement = select(chapters.c.id).where(
            chapters.c.class_id == class_id, chapters.c.id == chapter_id
        )
        return (
            connection.scalar(statement.with_for_update() if lock else statement)
            is not None
        )

    def add_question(self, connection, question, version, actor_id, now):
        connection.execute(insert(questions).values(question))
        connection.execute(insert(question_versions).values(version))
        self.audit_question(
            connection,
            question["class_id"],
            question["id"],
            1,
            actor_id,
            "created",
            now,
        )

    def edit_question(self, connection, class_id, question_id, version, actor_id, now):
        connection.execute(insert(question_versions).values(version))
        connection.execute(
            update(questions)
            .where(questions.c.id == question_id)
            .values(
                current_version=version["version"],
                reviewed_version=None,
                updated_at=now,
            )
        )
        self.audit_question(
            connection,
            class_id,
            question_id,
            version["version"],
            actor_id,
            "edited",
            now,
        )

    def review_question(
        self, connection, class_id, question_id, version, actor_id, now
    ):
        connection.execute(
            update(questions)
            .where(questions.c.id == question_id)
            .values(reviewed_version=version, updated_at=now)
        )
        self.audit_question(
            connection, class_id, question_id, version, actor_id, "reviewed", now
        )

    def audit_question(
        self, connection, class_id, question_id, version, actor_id, event, now
    ):
        from uuid import uuid4

        connection.execute(
            insert(question_audits).values(
                id=str(uuid4()),
                class_id=class_id,
                question_id=question_id,
                version=version,
                actor_id=actor_id,
                event=event,
                created_at=now,
            )
        )

    def quiz(self, connection, class_id, quiz_id, *, lock=False):
        statement = select(quizzes).where(
            quizzes.c.class_id == class_id, quizzes.c.id == quiz_id
        )
        if lock:
            statement = statement.with_for_update()
        return connection.execute(statement).mappings().one_or_none()

    def list_quizzes(
        self,
        class_id,
        actor_id,
        teacher,
        page,
        page_size,
        *,
        published_only=False,
        chapter_id=None,
    ):
        with self.engine.connect() as connection:
            scope = quizzes.c.class_id == class_id
            if chapter_id is not None:
                scope &= quizzes.c.chapter_id == chapter_id
            if published_only:
                scope &= quizzes.c.published_at.is_not(None)
            statement = select(quizzes).where(scope)
            count = select(func.count()).select_from(quizzes).where(scope)
            if not teacher:
                eligibility = (quiz_participants.c.class_id == class_id) & (
                    quiz_participants.c.student_id == actor_id
                )
                statement = statement.join(
                    quiz_participants, quiz_participants.c.quiz_id == quizzes.c.id
                ).where(eligibility, quizzes.c.published_at.is_not(None))
                count = count.join(
                    quiz_participants, quiz_participants.c.quiz_id == quizzes.c.id
                ).where(eligibility, quizzes.c.published_at.is_not(None))
            total = connection.scalar(count)
            rows = (
                connection.execute(
                    statement.order_by(quizzes.c.created_at.desc(), quizzes.c.id)
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
                .mappings()
                .all()
            )
        return rows, total

    def draft_items(self, connection, class_id, quiz_id):
        return (
            connection.execute(
                select(quiz_draft_items)
                .where(
                    quiz_draft_items.c.class_id == class_id,
                    quiz_draft_items.c.quiz_id == quiz_id,
                )
                .order_by(quiz_draft_items.c.position)
            )
            .mappings()
            .all()
        )

    def items(self, connection, class_id, quiz_id):
        return (
            connection.execute(
                select(quiz_items)
                .where(
                    quiz_items.c.class_id == class_id, quiz_items.c.quiz_id == quiz_id
                )
                .order_by(quiz_items.c.position)
            )
            .mappings()
            .all()
        )

    def participant(self, connection, class_id, quiz_id, student_id, *, lock=False):
        statement = select(quiz_participants).where(
            quiz_participants.c.class_id == class_id,
            quiz_participants.c.quiz_id == quiz_id,
            quiz_participants.c.student_id == student_id,
        )
        if lock:
            statement = statement.with_for_update()
        return connection.execute(statement).mappings().one_or_none()

    def students(self, connection, class_id):
        return (
            connection.execute(
                select(accounts.c.id)
                .where(
                    accounts.c.class_id == class_id,
                    accounts.c.role == "student",
                    accounts.c.enabled.is_(True),
                )
                .order_by(accounts.c.id)
                .with_for_update()
            )
            .scalars()
            .all()
        )

    def create_quiz(self, connection, quiz, items, now):
        connection.execute(insert(quizzes).values(quiz))
        connection.execute(insert(quiz_draft_items), items)
        self.audit_quiz(
            connection, quiz["class_id"], quiz["id"], quiz["creator_id"], "created", now
        )

    def publish(self, connection, quiz, items, students, actor_id, now):
        connection.execute(insert(quiz_items), items)
        connection.execute(
            insert(quiz_participants),
            [
                {
                    "quiz_id": quiz["id"],
                    "class_id": quiz["class_id"],
                    "student_id": student_id,
                    "created_at": now,
                }
                for student_id in students
            ],
        )
        connection.execute(
            update(quizzes).where(quizzes.c.id == quiz["id"]).values(published_at=now)
        )
        self.audit_quiz(
            connection, quiz["class_id"], quiz["id"], actor_id, "published", now
        )

    def draft(self, connection, class_id, quiz_id, student_id, *, lock=False):
        statement = select(quiz_drafts).where(
            quiz_drafts.c.class_id == class_id,
            quiz_drafts.c.quiz_id == quiz_id,
            quiz_drafts.c.student_id == student_id,
        )
        if lock:
            statement = statement.with_for_update()
        return connection.execute(statement).mappings().one_or_none()

    def save_draft(
        self, connection, class_id, quiz_id, student_id, answers, revision, now
    ):
        if revision == 1:
            connection.execute(
                insert(quiz_drafts).values(
                    class_id=class_id,
                    quiz_id=quiz_id,
                    student_id=student_id,
                    answers=answers,
                    revision=revision,
                    updated_at=now,
                )
            )
        else:
            connection.execute(
                update(quiz_drafts)
                .where(
                    quiz_drafts.c.class_id == class_id,
                    quiz_drafts.c.quiz_id == quiz_id,
                    quiz_drafts.c.student_id == student_id,
                )
                .values(answers=answers, revision=revision, updated_at=now)
            )

    def submission(self, connection, class_id, quiz_id, student_id):
        return (
            connection.execute(
                select(quiz_submissions).where(
                    quiz_submissions.c.class_id == class_id,
                    quiz_submissions.c.quiz_id == quiz_id,
                    quiz_submissions.c.student_id == student_id,
                )
            )
            .mappings()
            .one_or_none()
        )

    def result(self, connection, submission_id):
        return (
            connection.execute(
                select(quiz_results).where(
                    quiz_results.c.submission_id == submission_id
                )
            )
            .mappings()
            .one_or_none()
        )

    def submit(self, connection, submission, result, now):
        connection.execute(insert(quiz_submissions).values(submission))
        connection.execute(insert(quiz_results).values(result))
        self.audit_quiz(
            connection,
            submission["class_id"],
            submission["quiz_id"],
            submission["student_id"],
            "submitted",
            now,
        )

    def list_results(self, connection, class_id, quiz_id, page, page_size):
        scope = (quiz_submissions.c.class_id == class_id) & (
            quiz_submissions.c.quiz_id == quiz_id
        )
        total = connection.scalar(
            select(func.count()).select_from(quiz_submissions).where(scope)
        )
        rows = (
            connection.execute(
                select(
                    quiz_submissions.c.id,
                    quiz_submissions.c.student_id,
                    quiz_submissions.c.answers,
                    quiz_submissions.c.accepted_at,
                    quiz_results.c.score,
                    quiz_results.c.max_score,
                    quiz_results.c.details,
                )
                .join(
                    quiz_results, quiz_results.c.submission_id == quiz_submissions.c.id
                )
                .where(scope)
                .order_by(quiz_submissions.c.accepted_at, quiz_submissions.c.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            .mappings()
            .all()
        )
        return rows, total

    def insight_rows(self, connection, class_id, quiz_id):
        participants = connection.scalar(
            select(func.count())
            .select_from(quiz_participants)
            .where(
                quiz_participants.c.class_id == class_id,
                quiz_participants.c.quiz_id == quiz_id,
            )
        )
        rows = (
            connection.execute(
                select(quiz_results.c.score, quiz_results.c.details)
                .join(
                    quiz_submissions,
                    quiz_submissions.c.id == quiz_results.c.submission_id,
                )
                .where(
                    quiz_submissions.c.class_id == class_id,
                    quiz_submissions.c.quiz_id == quiz_id,
                )
            )
            .mappings()
            .all()
        )
        return participants, rows

    def unresolved_count(self, connection, class_id, chapter_id, now):
        from app.adapters.assistant_schema_v8 import feedback

        query = FeedbackRepositoryMixin.feedback_query(class_id, now).where(
            feedback.c.chapter_id == chapter_id,
            feedback.c.rating == "unresolved",
            feedback.c.status == "pending",
        )
        return connection.scalar(select(func.count()).select_from(query.subquery()))

    def audit_quiz(self, connection, class_id, quiz_id, actor_id, event, now):
        from uuid import uuid4

        connection.execute(
            insert(quiz_audits).values(
                id=str(uuid4()),
                class_id=class_id,
                quiz_id=quiz_id,
                actor_id=actor_id,
                event=event,
                created_at=now,
            )
        )
