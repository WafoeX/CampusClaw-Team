"""人工题库、不可变测验和 MySQL 内确定性评分。"""

import json
from datetime import UTC
from hashlib import sha256
from uuid import uuid4

from app.services.access import AccessDenied
from app.services.auth import digest_cookie, invalid_session, utc_now
from app.services.materials import missing, unavailable

TEACHING_WRITE = "teaching:write"
TEACHING_ANSWER = "teaching:answer"


def invalid(message="请检查教学参数"):
    return AccessDenied(400, 1000, message)


def conflict(message="状态或修订已变化，请刷新后重试", code=1400):
    return AccessDenied(409, code, message)


def iso(value):
    return value.replace(tzinfo=UTC).isoformat() if value is not None else None


def question_view(row, version):
    return {
        "id": row["id"],
        "version": row["current_version"],
        "reviewed": row["reviewed_version"] == row["current_version"],
        "kind": version["kind"],
        "stem": version["stem"],
        "options": version["options"],
        "answer": version["answer"],
        "explanation": version["explanation"],
        "source_material_id": version["source_material_id"],
        "origin": "ai" if row.get("job_id") else "manual",
    }


def quiz_view(row, items, *, teacher, now):
    published = row["published_at"] is not None
    result = {
        "id": row["id"],
        "title": row["title"],
        "chapter_id": row["chapter_id"],
        "published": published,
        "published_at": iso(row["published_at"]),
        "deadline_at": iso(row["deadline_at"]),
        "answers_open_at": iso(row["answers_open_at"]),
        "server_time": iso(now),
    }
    if not published:
        result["items"] = [
            {"question_id": item["question_id"], "points": item["points"]}
            for item in items
        ]
    else:
        result["items"] = [
            {
                "id": item["id"],
                "position": item["position"],
                "kind": item["kind"],
                "stem": item["stem"],
                "options": item["options"],
                "points": item["points"],
                **(
                    {
                        "answer": item["answer"],
                        "explanation": item["explanation"],
                        "source_material_id": item["source_material_id"],
                    }
                    if teacher
                    else {}
                ),
            }
            for item in items
        ]
    return result


class TeachingService:
    def __init__(self, repository, database_error, clock=utc_now):
        self.repository = repository
        self.database_error = database_error
        self.clock = clock

    def _actor(self, connection, identity, cookie, role):
        digest = digest_cookie(cookie)
        if digest is None:
            raise invalid_session()
        actor = self.repository.lock_actor(
            connection, identity.subject_id, digest, self.clock
        )
        if actor is None:
            raise invalid_session()
        if actor.class_id != identity.class_id or actor.role != role:
            raise AccessDenied(403, 1200, "当前账号无此操作权限")

    def _question(self, connection, identity, question_id, *, lock=False):
        row = self.repository.question(
            connection, identity.class_id, question_id, lock=lock
        )
        if row is None:
            raise missing()
        return row

    def _manual_source(self, connection, identity, fields):
        source = fields.get("source_material_id")
        if source is None:
            return None
        material = self.repository.source_material(
            connection, identity.class_id, source, lock=True
        )
        if material is None:
            raise missing()
        return {
            "title": material["title"],
            "source_version": material["content_version"],
            "index_version": material["active_index_version"],
        }

    def create_question(self, identity, cookie, fields):
        try:
            with self.repository.transaction() as connection:
                self._actor(connection, identity, cookie, "teacher")
                snapshot = self._manual_source(connection, identity, fields)
                now = self.repository.now(connection)
                question = {
                    "id": str(uuid4()),
                    "class_id": identity.class_id,
                    "creator_id": identity.subject_id,
                    "current_version": 1,
                    "reviewed_version": None,
                    "created_at": now,
                    "updated_at": now,
                }
                version = {
                    "question_id": question["id"],
                    "class_id": identity.class_id,
                    "version": 1,
                    "created_at": now,
                    **fields,
                }
                self.repository.add_question(
                    connection, question, version, identity.subject_id, now
                )
                if snapshot is not None:
                    self.repository.save_source(connection, version, snapshot)
                return question_view(question, version)
        except self.database_error:
            raise unavailable() from None

    def edit_question(self, identity, cookie, question_id, expected_version, fields):
        try:
            with self.repository.transaction() as connection:
                self._actor(connection, identity, cookie, "teacher")
                row = self._question(connection, identity, question_id, lock=True)
                if row["current_version"] != expected_version:
                    raise conflict()
                snapshot = self._manual_source(connection, identity, fields)
                now = self.repository.now(connection)
                version = {
                    "question_id": question_id,
                    "class_id": identity.class_id,
                    "version": expected_version + 1,
                    "created_at": now,
                    **fields,
                }
                self.repository.edit_question(
                    connection,
                    identity.class_id,
                    question_id,
                    version,
                    identity.subject_id,
                    now,
                )
                if snapshot is not None:
                    self.repository.save_source(connection, version, snapshot)
                return question_view(
                    {
                        **row,
                        "current_version": version["version"],
                        "reviewed_version": None,
                    },
                    version,
                )
        except self.database_error:
            raise unavailable() from None

    def review_question(self, identity, cookie, question_id, expected_version):
        try:
            with self.repository.transaction() as connection:
                self._actor(connection, identity, cookie, "teacher")
                row = self._question(connection, identity, question_id, lock=True)
                if (
                    row["current_version"] != expected_version
                    or row["reviewed_version"] == expected_version
                ):
                    raise conflict()
                now = self.repository.now(connection)
                self.repository.review_question(
                    connection,
                    identity.class_id,
                    question_id,
                    expected_version,
                    identity.subject_id,
                    now,
                )
                version = self.repository.version(
                    connection, identity.class_id, question_id, expected_version
                )
                return question_view(
                    {**row, "reviewed_version": expected_version}, version
                )
        except self.database_error:
            raise unavailable() from None

    def read_question(self, identity, question_id):
        try:
            with self.repository.engine.connect() as connection:
                row = self._question(connection, identity, question_id)
                version = self.repository.version(
                    connection, identity.class_id, question_id, row["current_version"]
                )
                view = question_view(row, version)
                if version["source_material_id"] is not None:
                    view["source_snapshot"] = self.repository.source_snapshot(
                        connection,
                        identity.class_id,
                        question_id,
                        row["current_version"],
                        version["source_material_id"],
                    )
                return view
        except self.database_error:
            raise unavailable() from None

    def list_questions(self, identity, page, page_size):
        try:
            rows, total = self.repository.list_questions(
                identity.class_id, page, page_size
            )
        except self.database_error:
            raise unavailable() from None
        return {
            "items": [
                {
                    "id": row["id"],
                    "version": row["current_version"],
                    "reviewed": row["reviewed_version"] == row["current_version"],
                    "kind": row["kind"],
                    "stem": row["stem"],
                    "origin": "ai" if row.get("job_id") else "manual",
                }
                for row in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def _quiz(self, connection, identity, quiz_id, *, teacher, lock=False):
        row = self.repository.quiz(connection, identity.class_id, quiz_id, lock=lock)
        if row is None or (
            not teacher
            and (
                row["published_at"] is None
                or self.repository.participant(
                    connection, identity.class_id, quiz_id, identity.subject_id
                )
                is None
            )
        ):
            raise missing()
        return row

    def create_quiz(
        self,
        identity,
        cookie,
        title,
        chapter_id,
        deadline_at,
        answers_open_at,
        item_specs,
    ):
        try:
            with self.repository.transaction() as connection:
                self._actor(connection, identity, cookie, "teacher")
                if chapter_id is not None and not self.repository.chapter_exists(
                    connection, identity.class_id, chapter_id
                ):
                    raise missing()
                for spec in item_specs:
                    self._question(connection, identity, spec["question_id"])
                now = self.repository.now(connection)
                if not now < deadline_at <= answers_open_at:
                    raise invalid("截止时间须晚于当前时间，答案开放不得早于截止")
                quiz = {
                    "id": str(uuid4()),
                    "class_id": identity.class_id,
                    "chapter_id": chapter_id,
                    "creator_id": identity.subject_id,
                    "title": title,
                    "deadline_at": deadline_at,
                    "answers_open_at": answers_open_at,
                    "published_at": None,
                    "created_at": now,
                }
                items = [
                    {
                        "quiz_id": quiz["id"],
                        "class_id": identity.class_id,
                        "position": position,
                        **spec,
                    }
                    for position, spec in enumerate(item_specs, 1)
                ]
                self.repository.create_quiz(connection, quiz, items, now)
                return quiz_view(quiz, items, teacher=True, now=now)
        except self.database_error:
            raise unavailable() from None

    def publish_quiz(self, identity, cookie, quiz_id):
        try:
            with self.repository.transaction() as connection:
                self._actor(connection, identity, cookie, "teacher")
                quiz = self._quiz(
                    connection, identity, quiz_id, teacher=True, lock=True
                )
                if quiz["published_at"] is not None:
                    raise conflict("测验已经发布")
                now = self.repository.now(connection)
                if not now < quiz["deadline_at"] <= quiz["answers_open_at"]:
                    raise conflict("截止时间已到，无法发布")
                specs = self.repository.draft_items(
                    connection, identity.class_id, quiz_id
                )
                students = self.repository.students(connection, identity.class_id)
                if not specs or not students:
                    raise invalid("测验须有题目和至少一名参与学生")
                items = []
                for spec in specs:
                    question = self._question(
                        connection, identity, spec["question_id"], lock=True
                    )
                    if question["reviewed_version"] != question["current_version"]:
                        raise conflict("题目修订尚未审核")
                    version = self.repository.version(
                        connection,
                        identity.class_id,
                        question["id"],
                        question["current_version"],
                    )
                    items.append(
                        {
                            "id": str(uuid4()),
                            "quiz_id": quiz_id,
                            "class_id": identity.class_id,
                            "position": spec["position"],
                            "question_id": question["id"],
                            "question_version": question["current_version"],
                            "kind": version["kind"],
                            "stem": version["stem"],
                            "options": version["options"],
                            "answer": version["answer"],
                            "explanation": version["explanation"],
                            "source_material_id": version["source_material_id"],
                            "points": spec["points"],
                            "scoring_version": 1,
                        }
                    )
                self.repository.publish(
                    connection, quiz, items, students, identity.subject_id, now
                )
                return quiz_view(
                    {**quiz, "published_at": now}, items, teacher=True, now=now
                )
        except self.database_error:
            raise unavailable() from None

    def read_quiz(self, identity, quiz_id, *, teacher):
        try:
            with self.repository.engine.connect() as connection:
                quiz = self._quiz(connection, identity, quiz_id, teacher=teacher)
                items = (
                    self.repository.items
                    if quiz["published_at"]
                    else self.repository.draft_items
                )(connection, identity.class_id, quiz_id)
                return quiz_view(
                    quiz, items, teacher=teacher, now=self.repository.now(connection)
                )
        except self.database_error:
            raise unavailable() from None

    def list_quizzes(self, identity, *, teacher, page, page_size):
        try:
            rows, total = self.repository.list_quizzes(
                identity.class_id, identity.subject_id, teacher, page, page_size
            )
        except self.database_error:
            raise unavailable() from None
        return {
            "items": [
                {
                    "id": row["id"],
                    "title": row["title"],
                    "published": row["published_at"] is not None,
                    "deadline_at": iso(row["deadline_at"]),
                    "answers_open_at": iso(row["answers_open_at"]),
                }
                for row in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def _student_quiz(self, connection, identity, quiz_id, *, lock=False):
        quiz = self._quiz(connection, identity, quiz_id, teacher=False)
        if lock:
            participant = self.repository.participant(
                connection, identity.class_id, quiz_id, identity.subject_id, lock=True
            )
            if participant is None:
                raise missing()
        return quiz

    @staticmethod
    def _validate_answers(answers, items):
        permitted = {item["id"]: item for item in items}
        if not isinstance(answers, dict) or len(answers) > len(items):
            raise invalid("作答格式无效")
        for item_id, value in answers.items():
            item = permitted.get(item_id)
            if item is None or not isinstance(value, str):
                raise invalid("作答包含题外标识或非法选项")
            if item["kind"] == "single_choice":
                if value not in [
                    chr(65 + index) for index in range(len(item["options"]))
                ]:
                    raise invalid("单选答案无效")
            elif value not in {"true", "false"}:
                raise invalid("判断答案无效")

    def read_draft(self, identity, quiz_id):
        try:
            with self.repository.engine.connect() as connection:
                quiz = self._student_quiz(connection, identity, quiz_id)
                draft = self.repository.draft(
                    connection, identity.class_id, quiz_id, identity.subject_id
                )
                submitted = self.repository.submission(
                    connection, identity.class_id, quiz_id, identity.subject_id
                )
                now = self.repository.now(connection)
                return {
                    "revision": draft["revision"] if draft else 0,
                    "answers": draft["answers"] if draft else {},
                    "submitted": submitted is not None,
                    "deadline_at": iso(quiz["deadline_at"]),
                    "server_time": iso(now),
                }
        except self.database_error:
            raise unavailable() from None

    def save_draft(self, identity, cookie, quiz_id, expected_revision, answers):
        try:
            with self.repository.transaction() as connection:
                self._actor(connection, identity, cookie, "student")
                quiz = self._student_quiz(connection, identity, quiz_id, lock=True)
                items = self.repository.items(connection, identity.class_id, quiz_id)
                self._validate_answers(answers, items)
                draft = self.repository.draft(
                    connection,
                    identity.class_id,
                    quiz_id,
                    identity.subject_id,
                    lock=True,
                )
                if expected_revision != (draft["revision"] if draft else 0):
                    raise conflict("草稿修订已变化")
                if self.repository.submission(
                    connection, identity.class_id, quiz_id, identity.subject_id
                ):
                    raise conflict("已正式提交", 1401)
                now = self.repository.now(connection)
                if now >= quiz["deadline_at"]:
                    raise conflict("提交截止时间已到", 1402)
                revision = expected_revision + 1
                self.repository.save_draft(
                    connection,
                    identity.class_id,
                    quiz_id,
                    identity.subject_id,
                    answers,
                    revision,
                    now,
                )
                return {
                    "revision": revision,
                    "answers": answers,
                    "server_time": iso(now),
                }
        except self.database_error:
            raise unavailable() from None

    def submit(self, identity, cookie, quiz_id, request_key, draft_revision, answers):
        try:
            with self.repository.transaction() as connection:
                self._actor(connection, identity, cookie, "student")
                quiz = self._student_quiz(connection, identity, quiz_id, lock=True)
                items = self.repository.items(connection, identity.class_id, quiz_id)
                self._validate_answers(answers, items)
                fingerprint = sha256(
                    json.dumps(
                        {"answers": answers, "draft_revision": draft_revision},
                        sort_keys=True,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ).encode()
                ).digest()
                prior = self.repository.submission(
                    connection, identity.class_id, quiz_id, identity.subject_id
                )
                if prior is not None:
                    if (
                        prior["request_key"] == request_key
                        and prior["fingerprint"] == fingerprint
                    ):
                        return {
                            "submission_id": prior["id"],
                            "accepted_at": iso(prior["accepted_at"]),
                        }
                    if prior["request_key"] == request_key:
                        raise conflict("请求标识已用于不同作答")
                    raise conflict("已正式提交", 1401)
                draft = self.repository.draft(
                    connection,
                    identity.class_id,
                    quiz_id,
                    identity.subject_id,
                    lock=True,
                )
                if draft_revision != (draft["revision"] if draft else 0):
                    raise conflict("草稿修订已变化")
                now = self.repository.now(connection)
                if now >= quiz["deadline_at"]:
                    raise conflict("提交截止时间已到", 1402)
                details = [
                    {
                        "item_id": item["id"],
                        "correct": answers.get(item["id"]) == item["answer"],
                        "awarded_points": item["points"]
                        if answers.get(item["id"]) == item["answer"]
                        else 0,
                    }
                    for item in items
                ]
                submission = {
                    "id": str(uuid4()),
                    "quiz_id": quiz_id,
                    "class_id": identity.class_id,
                    "student_id": identity.subject_id,
                    "request_key": request_key,
                    "fingerprint": fingerprint,
                    "answers": answers,
                    "accepted_at": now,
                }
                result = {
                    "submission_id": submission["id"],
                    "score": sum(detail["awarded_points"] for detail in details),
                    "max_score": sum(item["points"] for item in items),
                    "details": details,
                    "scoring_version": 1,
                    "created_at": now,
                }
                self.repository.submit(connection, submission, result, now)
                return {"submission_id": submission["id"], "accepted_at": iso(now)}
        except self.database_error:
            raise unavailable() from None

    def my_submission(self, identity, quiz_id):
        try:
            with self.repository.engine.connect() as connection:
                quiz = self._student_quiz(connection, identity, quiz_id)
                submission = self.repository.submission(
                    connection, identity.class_id, quiz_id, identity.subject_id
                )
                now = self.repository.now(connection)
                if submission is None:
                    return {"submitted": False, "server_time": iso(now)}
                projection = {
                    "submitted": True,
                    "submission_id": submission["id"],
                    "answers": submission["answers"],
                    "accepted_at": iso(submission["accepted_at"]),
                    "server_time": iso(now),
                }
                if now >= quiz["answers_open_at"]:
                    result = self.repository.result(connection, submission["id"])
                    if result is not None:
                        items = self.repository.items(
                            connection, identity.class_id, quiz_id
                        )
                        projection.update(
                            {
                                "score": result["score"],
                                "max_score": result["max_score"],
                                "details": [
                                    {
                                        **detail,
                                        "answer": item["answer"],
                                        "explanation": item["explanation"],
                                        "source_material_id": item[
                                            "source_material_id"
                                        ],
                                    }
                                    for detail, item in zip(
                                        result["details"], items, strict=True
                                    )
                                ],
                            }
                        )
                return projection
        except self.database_error:
            raise unavailable() from None

    def submission_results(self, identity, quiz_id, page, page_size):
        try:
            with self.repository.engine.connect() as connection:
                self._quiz(connection, identity, quiz_id, teacher=True)
                rows, total = self.repository.list_results(
                    connection, identity.class_id, quiz_id, page, page_size
                )
                return {
                    "items": [
                        {
                            "submission_id": row["id"],
                            "student_id": row["student_id"],
                            "answers": row["answers"],
                            "accepted_at": iso(row["accepted_at"]),
                            "score": row["score"],
                            "max_score": row["max_score"],
                            "details": row["details"],
                        }
                        for row in rows
                    ],
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                }
        except self.database_error:
            raise unavailable() from None

    def my_mistakes(self, identity, quiz_id):
        result = self.my_submission(identity, quiz_id)
        if "details" not in result:
            return {"open": False, "items": []}
        try:
            with self.repository.engine.connect() as connection:
                items = {
                    row["id"]: row
                    for row in self.repository.items(
                        connection, identity.class_id, quiz_id
                    )
                }
                mistakes = []
                for detail in result["details"]:
                    if detail["correct"]:
                        continue
                    item = items[detail["item_id"]]
                    source = item["source_material_id"]
                    snapshot = (
                        self.repository.source_snapshot(
                            connection,
                            identity.class_id,
                            item["question_id"],
                            item["question_version"],
                            source,
                        )
                        if source is not None
                        else None
                    )
                    mistakes.append(
                        {
                            "item_id": item["id"],
                            "stem": item["stem"],
                            "options": item["options"],
                            "submitted_answer": result["answers"].get(item["id"]),
                            "answer": detail["answer"],
                            "explanation": detail["explanation"],
                            "source_material_id": source,
                            "source_status": "available" if snapshot else "unavailable",
                            "source_snapshot": snapshot,
                        }
                    )
                return {"open": True, "items": mistakes}
        except self.database_error:
            raise unavailable() from None

    def insights(self, identity, quiz_id):
        try:
            with self.repository.engine.connect() as connection:
                quiz = self._quiz(connection, identity, quiz_id, teacher=True)
                if quiz["published_at"] is None:
                    raise conflict("测验尚未发布")
                items = self.repository.items(connection, identity.class_id, quiz_id)
                participants, rows = self.repository.insight_rows(
                    connection, identity.class_id, quiz_id
                )
                count = len(rows)
                correct = {item["id"]: 0 for item in items}
                for row in rows:
                    for detail in row["details"]:
                        if detail["item_id"] in correct and detail["correct"]:
                            correct[detail["item_id"]] += 1
                now = self.repository.now(connection)
                unresolved = (
                    self.repository.unresolved_count(
                        connection, identity.class_id, quiz["chapter_id"], now
                    )
                    if quiz["chapter_id"] is not None
                    else None
                )
                return {
                    "quiz_id": quiz_id,
                    "participants": participants,
                    "submissions": count,
                    "submission_rate": round(100 * count / participants, 2)
                    if participants
                    else None,
                    "average_score": round(sum(row["score"] for row in rows) / count, 2)
                    if count
                    else None,
                    "item_accuracy": [
                        {
                            "item_id": item["id"],
                            "position": item["position"],
                            "correct_rate": round(100 * correct[item["id"]] / count, 2)
                            if count
                            else None,
                        }
                        for item in items
                    ],
                    "unresolved_count": unresolved,
                    "feedback_status": "available"
                    if quiz["chapter_id"] is not None
                    else "no_chapter",
                }
        except self.database_error:
            raise unavailable() from None

    def summaries(
        self, identity, *, teacher, page, page_size, chapter_id=None, quiz_id=None
    ):
        try:
            if chapter_id is not None or quiz_id is not None:
                with self.repository.engine.connect() as connection:
                    if chapter_id is not None and not self.repository.chapter_exists(
                        connection, identity.class_id, chapter_id
                    ):
                        raise invalid("章节筛选无效")
                    if quiz_id is not None:
                        quiz = self._quiz(
                            connection, identity, quiz_id, teacher=teacher
                        )
                        if chapter_id is not None and quiz["chapter_id"] != chapter_id:
                            raise invalid("章节与测验筛选不一致")
                        if quiz["published_at"] is None:
                            raise invalid("测验尚未发布")
            if quiz_id is not None:
                rows, total = ([quiz] if page == 1 else []), 1
            else:
                rows, total = self.repository.list_quizzes(
                    identity.class_id,
                    identity.subject_id,
                    teacher,
                    page,
                    page_size,
                    published_only=True,
                    chapter_id=chapter_id,
                )
            get_summary = self.insights if teacher else self.my_mistakes
            return {
                "items": [
                    {
                        "quiz_id": row["id"],
                        "title": row["title"],
                        **get_summary(identity, row["id"]),
                    }
                    for row in rows
                ],
                "total": total,
                "page": page,
                "page_size": page_size,
            }
        except self.database_error:
            raise unavailable() from None
