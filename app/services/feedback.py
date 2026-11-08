"""本人历史出处及学生主动分享的最小教学反馈；从不调用模型。"""

from uuid import uuid4

from app.services.access import AccessDenied
from app.services.ai_contracts import bad, clean_text, conflict
from app.services.materials import missing, unavailable


def expected_revision(value):
    if type(value) is not int or value < 0 or value > 2_147_483_647:
        raise bad()
    return value


def feedback_input(payload):
    if (
        not isinstance(payload, dict)
        or payload.keys() - {"rating", "note", "expected_revision"}
        or not {"rating", "expected_revision"} <= payload.keys()
    ):
        raise bad()
    rating = payload["rating"]
    if not isinstance(rating, str) or rating not in ("helpful", "unresolved"):
        raise bad()
    note = clean_text(payload.get("note", ""), 500, empty=rating == "helpful")
    return rating, note or None, expected_revision(payload["expected_revision"])


def feedback_view(row):
    return {key: row[key] for key in ("id", "rating", "note", "status", "revision")} | {
        "chapter": row.get("chapter_name"),
        "updated_at": row["updated_at"].isoformat() + "Z",
    }


class FeedbackService:
    def __init__(self, sessions):
        self.sessions = sessions
        self.ai = sessions.ai
        self.repository = sessions.repository

    def _message(self, connection, identity, session_id, message_id):
        self.sessions._session(connection, identity, session_id)
        row = self.repository.lock_message(
            connection, identity, session_id, message_id, self.ai.clock()
        )
        if row is None:
            raise missing()
        return row

    def citation(self, identity, cookie, session_id, message_id, ordinal):
        if type(ordinal) is not int or not 1 <= ordinal <= 4:
            raise bad()
        try:
            with self.repository.transaction() as connection:
                self.ai._actor(connection, identity, cookie)
                message = self._message(connection, identity, session_id, message_id)
                refs, safe = self.sessions._sources(connection, identity, message_id)
                ref = next((item for item in refs if item["ordinal"] == ordinal), None)
                if ref is None:
                    raise missing()
                if not safe or message["content_state"] != "available":
                    return {
                        "number": ordinal,
                        "status": "deleted"
                        if ref["status"] == "deleted" or not ref["current_material_id"]
                        else "unavailable",
                        "title": None,
                        "excerpt": None,
                        "location": None,
                    }
                historical = (
                    ref["source_version"] != ref["current_source_version"]
                    or ref["index_version"] != ref["current_index_version"]
                )
                return {
                    "number": ordinal,
                    "status": "historical" if historical else "available",
                    "title": ref["title"],
                    "excerpt": ref["excerpt"],
                    "location": {
                        "source_version": ref["source_version"],
                        "index_version": ref["index_version"],
                        "start": ref["start_offset"],
                        "end": ref["end_offset"],
                    },
                }
        except self.ai.database_error:
            raise unavailable() from None

    def put(self, identity, cookie, session_id, message_id, payload):
        rating, note, revision = feedback_input(payload)
        try:
            with self.repository.transaction() as connection:
                actor = self.ai._actor(connection, identity, cookie)
                if actor.role != "student":
                    raise AccessDenied(403, 1200, "当前账号无此操作权限")
                message = self._message(connection, identity, session_id, message_id)
                _, safe = self.sessions._sources(connection, identity, message_id)
                if (
                    message["role"] != "assistant"
                    or message["content_state"] != "available"
                    or not safe
                ):
                    raise conflict("只能评价当前可读的成功助手消息")
                prior = self.repository.message_feedback(connection, message_id)
                now = self.ai.clock()
                if prior is not None:
                    if prior["expires_at"] <= now or prior["status"] == "unavailable":
                        raise conflict()
                    if prior["rating"] == rating and prior["note"] == note:
                        return feedback_view(prior)
                    if prior["revision"] != revision:
                        raise conflict()
                elif revision != 0:
                    raise conflict()
                operation = self.repository.feedback_operation(
                    connection, message["operation_id"]
                )
                chapter = (operation["input_payload"] or {}).get("chapter_scope")
                if chapter == "uncategorized" or not self.repository.chapter_accessible(
                    connection, identity.class_id, chapter
                ):
                    chapter = None
                row = dict(
                    id=prior["id"] if prior else str(uuid4()),
                    class_id=identity.class_id,
                    owner_id=identity.subject_id,
                    creator_id=identity.subject_id,
                    session_id=session_id,
                    message_id=message_id,
                    chapter_id=chapter,
                    rating=rating,
                    note=note,
                    status="pending",
                    revision=prior["revision"] + 1 if prior else 1,
                    created_at=prior["created_at"] if prior else now,
                    updated_at=now,
                    expires_at=min(
                        message["expires_at"],
                        self.sessions._session(connection, identity, session_id)[
                            "expires_at"
                        ],
                    ),
                )
                self.repository.save_feedback(connection, row, new=prior is None)
                self.repository.feedback_audit(
                    connection, identity, row, "update" if prior else "create"
                )
                return feedback_view(row)
        except self.ai.database_error:
            raise unavailable() from None

    def list(self, identity, cookie, status, page, size):
        if status not in ("pending", "handled"):
            raise bad()
        try:
            with self.repository.transaction() as connection:
                self.ai._actor(connection, identity, cookie, teacher=True)
                rows, total = self.repository.teaching_feedback(
                    connection, identity.class_id, self.ai.clock(), status, page, size
                )
                return {
                    "items": [feedback_view(row) for row in rows],
                    "total": total,
                    "page": page,
                    "page_size": size,
                }
        except self.ai.database_error:
            raise unavailable() from None

    def handle(self, identity, cookie, feedback_id, payload):
        if (
            not isinstance(payload, dict)
            or payload.keys() != {"status", "expected_revision"}
            or payload["status"] != "handled"
        ):
            raise bad()
        revision = expected_revision(payload["expected_revision"])
        try:
            with self.repository.transaction() as connection:
                self.ai._actor(connection, identity, cookie, teacher=True)
                row = self.repository.lock_teaching_feedback(
                    connection, identity.class_id, self.ai.clock(), feedback_id
                )
                if row is None:
                    raise missing()
                if row["rating"] != "unresolved":
                    raise conflict()
                if row["status"] == "handled" and revision in (
                    row["revision"],
                    row["revision"] - 1,
                ):
                    return feedback_view(row)
                if row["revision"] != revision:
                    raise conflict()
                values = {
                    "id": row["id"],
                    "status": "handled",
                    "revision": revision + 1,
                    "updated_at": self.ai.clock(),
                }
                self.repository.save_feedback(connection, values, new=False)
                self.repository.feedback_audit(connection, identity, values, "handle")
                return feedback_view(dict(row) | values)
        except self.ai.database_error:
            raise unavailable() from None
