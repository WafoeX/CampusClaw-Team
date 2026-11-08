"""私有会话与轮次事务契约；受理、证据和条件提交可由SSE宿主复用。"""

import re
import time
from datetime import timedelta
from uuid import NAMESPACE_URL, uuid4, uuid5

from app.services.ai_contracts import (
    DEFAULT_ROLE,
    bad,
    clean_text,
    conflict,
    fingerprint,
    identifier,
)
from app.services.answer_validation import (
    NO_EVIDENCE,
    assemble_evidence,
    validate_claims,
)
from app.services.materials import missing, unavailable
from app.services.skills import HINTS, render_selection, select_skill
from app.services.skills import NO_EVIDENCE as NO_GUIDANCE_EVIDENCE

KEY = re.compile(rb"[A-Za-z0-9_-]{1,64}")


def request_input(payload):
    if (
        not isinstance(payload, dict)
        or payload.keys() - {"question", "chapter_scope", "retrieval_mode"}
        or "question" not in payload
    ):
        raise bad()
    question = clean_text(payload["question"], 500)
    if len(question) < 2:
        raise bad("请输入2至500个码点的问题")
    chapter = payload.get("chapter_scope")
    if "chapter_scope" in payload and chapter != "uncategorized":
        identifier(chapter)
    mode = payload.get("retrieval_mode", "keyword")
    if not isinstance(mode, str) or mode not in ("keyword", "vector", "hybrid"):
        raise bad()
    return {"question": question, "chapter_scope": chapter, "retrieval_mode": mode}


def session_view(row):
    return {key: row[key] for key in ("id", "assistant_id", "mode")} | {
        key: row[key].isoformat() + "Z"
        for key in ("created_at", "updated_at", "expires_at")
    }


def valid_key(key):
    if not isinstance(key, bytes) or not KEY.fullmatch(key):
        raise bad("请使用有效的幂等标识")


class SessionService:
    def __init__(self, ai_apps, retrieval):
        self.ai = ai_apps
        self.repository = ai_apps.repository
        self.retrieval = retrieval

    def _session(self, connection, identity, session_id):
        row = self.repository.lock_session(connection, identity, session_id)
        if row is None or row["expires_at"] <= self.ai.clock():
            raise missing()
        return row

    def _expiry(self):
        if self.ai.expires_at is None or self.ai.expires_at <= self.ai.clock():
            raise unavailable()
        return self.ai.expires_at

    def create(self, identity, cookie, payload, key):
        valid_key(key)
        if not isinstance(payload, dict) or payload.keys() != {"assistant_id", "mode"}:
            raise bad()
        identifier(payload["assistant_id"])
        if not isinstance(payload["mode"], str) or payload["mode"] not in (
            "material_qa",
            "problem_guidance",
        ):
            raise bad()
        resource_id = str(
            uuid5(
                NAMESPACE_URL,
                "campusclaw-session:"
                + identity.class_id
                + ":"
                + identity.subject_id
                + ":"
                + key.decode(),
            )
        )
        try:
            with self.repository.transaction() as connection:
                self.ai._actor(connection, identity, cookie)
                prior = self.repository.lock_session(connection, identity, resource_id)
                if prior is not None:
                    if prior["expires_at"] <= self.ai.clock() or any(
                        prior[k] != payload[k] for k in payload
                    ):
                        raise conflict()
                    return session_view(prior), True
                expires = self._expiry()
                self.ai._configuration(
                    connection,
                    identity,
                    "assistant",
                    payload["assistant_id"],
                    teacher=False,
                )
                now = self.ai.clock()
                row = dict(
                    id=resource_id,
                    class_id=identity.class_id,
                    owner_id=identity.subject_id,
                    assistant_id=payload["assistant_id"],
                    mode=payload["mode"],
                    created_at=now,
                    updated_at=now,
                    expires_at=expires,
                )
                self.repository.insert_session(connection, row)
                return session_view(row), False
        except self.ai.database_error:
            raise unavailable() from None

    def list(self, identity, cookie, page, size):
        try:
            with self.repository.transaction() as connection:
                self.ai._actor(connection, identity, cookie)
                rows, total = self.repository.list_sessions(
                    connection, identity, self.ai.clock(), page, size
                )
                return {
                    "items": [session_view(row) for row in rows],
                    "total": total,
                    "page": page,
                    "page_size": size,
                }
        except self.ai.database_error:
            raise unavailable() from None

    def _sources(self, connection, identity, message_id):
        rows = self.repository.message_sources(connection, identity, message_id)
        safe = all(
            row["status"] == "available"
            and row["current_material_id"]
            and row["expires_at"] > self.ai.clock()
            for row in rows
        )
        return rows, safe

    def _message_available(self, connection, identity, message):
        if message["content_state"] != "available":
            return False
        target = (
            message
            if message["role"] == "assistant"
            else self.repository.completed_message(connection, message["operation_id"])
        )
        return target is None or self._sources(connection, identity, target["id"])[1]

    def read(self, identity, cookie, session_id, page=1, size=20):
        try:
            with self.repository.transaction() as connection:
                self.ai._actor(connection, identity, cookie)
                session = self._session(connection, identity, session_id)
                rows, total = self.repository.session_messages(
                    connection, identity, session_id, self.ai.clock(), page, size
                )
                items = []
                for row in rows:
                    refs, safe = self._sources(connection, identity, row["id"])
                    safe = safe and self._message_available(connection, identity, row)
                    state = row["content_state"] if safe else "revoked"
                    own_feedback = (
                        self.repository.message_feedback(connection, row["id"])
                        if row["role"] == "assistant"
                        else None
                    )
                    from app.services.feedback import feedback_view

                    items.append(
                        dict(
                            id=row["id"],
                            role=row["role"],
                            content=row["content"] if state == "available" else None,
                            content_state=state,
                            operation_id=row["operation_id"],
                            feedback_chapter=self.repository.feedback_chapter(
                                connection, row["operation_id"], identity.class_id
                            )
                            if row["role"] == "assistant"
                            else None,
                            feedback=feedback_view(own_feedback)
                            if own_feedback is not None
                            and own_feedback["expires_at"] > self.ai.clock()
                            and safe
                            else None,
                            citations=[
                                {
                                    "number": ref["ordinal"],
                                    "status": ref["status"]
                                    if ref["current_material_id"]
                                    else "deleted",
                                }
                                for ref in refs
                            ],
                            created_at=row["created_at"].isoformat() + "Z",
                        )
                    )
                return session_view(session) | {
                    "messages": items,
                    "total": total,
                    "page": page,
                    "page_size": size,
                }
        except self.ai.database_error:
            raise unavailable() from None

    def _configuration(self, connection, identity, session):
        row = self.ai._configuration(
            connection, identity, "assistant", session["assistant_id"], teacher=True
        )
        enabled = row["enabled"]
        skills = (
            self.repository.bound_skills(
                connection, identity.class_id, row["id"], row["revision"]
            )
            if enabled
            else []
        )
        configuration = self.ai.model_configuration | {
            "app_key": session["mode"],
            "assistant_id": row["id"],
            "assistant_revision": row["revision"],
            "assistant_enabled": enabled,
            "material_ids": row["material_ids"] if enabled else [],
            "skills": [
                {"id": skill["id"], "revision": skill["revision"]} for skill in skills
            ],
            "prompt_version": "private-sessions-v1",
        }
        return (
            configuration,
            row["prompt"] or DEFAULT_ROLE if enabled else DEFAULT_ROLE,
            skills,
        )

    def _prior(self, connection, identity, session, key, normalized):
        now = self.ai.clock()
        prior = self.repository.lock_session_operation(
            connection, identity, session["id"], key=key
        )
        if prior is not None:
            if (
                prior["fingerprint"] != fingerprint(normalized)
                or prior["expires_at"] <= now
            ):
                raise conflict()
            if prior["status"] == "succeeded":
                message = self.repository.completed_message(connection, prior["id"])
                if (
                    message is None
                    or message["content_state"] != "available"
                    or not self._sources(connection, identity, message["id"])[1]
                ):
                    raise conflict("历史来源已变化，请查看脱敏历史")
                run = self.repository.current_attempt(
                    connection, prior["id"], prior["attempt_count"]
                )
                refs, _ = self._sources(connection, identity, message["id"])
                return prior, {
                    "replayed": True,
                    "message_id": message["id"],
                    "text": message["content"],
                    "citations": [ref["ordinal"] for ref in refs],
                    "run_id": run["id"],
                }
            if prior["status"] == "revoked" or prior["attempt_count"] >= 3:
                raise conflict("已达尝试上限或来源不可用，请查看本人记录")
        for active in self.repository.active_session_operations(
            connection, identity, session["id"]
        ):
            if active["lease_expires_at"] > now:
                raise conflict("本会话仍在执行，请稍后回读")
            run = self.repository.current_attempt(
                connection, active["id"], active["attempt_count"]
            )
            self.repository.finish_attempt(
                connection,
                {"operation_id": active["id"], "run_id": run["id"]},
                status="interrupted",
                error_code=1500,
                now=now,
            )
        return prior, None

    def prepare(self, identity, cookie, session_id, key, payload, *, deadline=None):
        """内部宿主入口，检索前由宿主申请容量；不向HTTP暴露未经校验的成功写入。"""
        valid_key(key)
        normalized = request_input(payload)
        identifier(session_id)
        deadline = deadline or time.monotonic() + 35
        try:
            with self.repository.transaction() as connection:
                self.ai._actor(connection, identity, cookie)
                session = self._session(connection, identity, session_id)
                _, replay = self._prior(connection, identity, session, key, normalized)
                if replay:
                    return replay
                self._expiry()
                configuration, prompt, skills = self._configuration(
                    connection, identity, session
                )
            scoped = self.retrieval.for_materials(configuration["material_ids"])
            # 空绑定仍校验身份和章节，不请求向量或模型，也不退化至全班。
            if configuration["material_ids"]:
                result = scoped.search(
                    identity,
                    cookie,
                    normalized["question"],
                    normalized["retrieval_mode"],
                    normalized["chapter_scope"],
                    deadline=deadline,
                )
                evidence = assemble_evidence(result["items"][:4])
            else:
                scoped.identity(identity, cookie)
                scoped.scope(identity, normalized["chapter_scope"])
                evidence = []
            if time.monotonic() >= deadline:
                raise unavailable()
            with self.repository.transaction() as connection:
                self.ai._actor(connection, identity, cookie)
                session = self._session(connection, identity, session_id)
                prior, replay = self._prior(
                    connection, identity, session, key, normalized
                )
                if replay:
                    return replay
                current, _, _ = self._configuration(connection, identity, session)
                if current != configuration or not self.repository.lock_evidence(
                    connection, identity.class_id, evidence
                ):
                    raise conflict()
                selected = select_skill(normalized["question"], skills)
                now = self.ai.clock()
                expiry = min(
                    session["expires_at"],
                    self._expiry(),
                    prior["expires_at"] if prior else session["expires_at"],
                )
                operation_id = prior["id"] if prior else str(uuid4())
                attempt = prior["attempt_count"] + 1 if prior else 1
                token, run_id, message_id = str(uuid4()), str(uuid4()), str(uuid4())
                used = configuration | {
                    "skill": {"id": selected["id"], "revision": selected["revision"]}
                    if selected
                    else None
                }
                operation = dict(
                    id=operation_id,
                    class_id=identity.class_id,
                    owner_id=identity.subject_id,
                    session_id=session_id,
                    app_key=session["mode"],
                    operation_scope=session_id.encode(),
                    request_key=key,
                    fingerprint=fingerprint(normalized),
                    input_payload=normalized,
                    status="running",
                    attempt_count=attempt,
                    lease_token=token,
                    lease_expires_at=now + timedelta(seconds=35),
                    created_at=prior["created_at"] if prior else now,
                    updated_at=now,
                    expires_at=expiry,
                )
                run = dict(
                    id=run_id,
                    class_id=identity.class_id,
                    owner_id=identity.subject_id,
                    operation_id=operation_id,
                    attempt=attempt,
                    status="running",
                    configuration=used,
                    details=None,
                    created_at=now,
                    updated_at=now,
                    expires_at=expiry,
                )
                history = []
                for message in reversed(
                    self.repository.history(connection, identity, session_id, now)
                ):
                    if self._message_available(connection, identity, message):
                        history.append(
                            {
                                "role": message["role"],
                                "content": message["content"][:500],
                            }
                        )
                self.repository.insert_attempt(
                    connection, operation, run, new=prior is None
                )
                if prior is None:
                    self.repository.insert_user_message(
                        connection, operation, normalized["question"], str(uuid4())
                    )
                return dict(
                    replayed=False,
                    session_id=session_id,
                    operation_id=operation_id,
                    run_id=run_id,
                    message_id=message_id,
                    token=token,
                    expires_at=expiry,
                    configuration=configuration,
                    effective_prompt=prompt,
                    selected_skill=selected,
                    evidence=evidence,
                    history=history,
                    normalized=normalized,
                    attempt=attempt,
                    started=time.monotonic(),
                )
        except self.ai.database_error:
            raise unavailable() from None

    def _ticket(self, connection, identity, cookie, ticket):
        self.ai._actor(connection, identity, cookie)
        session = self._session(connection, identity, ticket["session_id"])
        row = self.repository.lock_session_operation(
            connection, identity, session["id"], operation_id=ticket["operation_id"]
        )
        if (
            row is None
            or row["status"] != "running"
            or row["lease_token"] != ticket["token"]
            or row["lease_expires_at"] <= self.ai.clock()
            or row["expires_at"] <= self.ai.clock()
        ):
            raise conflict()
        current, _, _ = self._configuration(connection, identity, session)
        if current != ticket["configuration"] or not self.repository.lock_evidence(
            connection, identity.class_id, ticket["evidence"]
        ):
            raise conflict()
        return row

    def recheck(self, identity, cookie, ticket):
        try:
            with self.repository.transaction() as connection:
                self._ticket(connection, identity, cookie, ticket)
            self.retrieval.for_materials(
                ticket["configuration"]["material_ids"]
            ).recheck(
                identity,
                cookie,
                ticket["evidence"],
                ticket["normalized"]["chapter_scope"],
            )
        except self.ai.database_error:
            raise unavailable() from None

    def finish(self, identity, cookie, ticket, payload, *, segments=None):
        """持久成功必须由本服务重验模型结构，不能相信调用方传入自由正文。"""
        steps = []
        if ticket["configuration"]["app_key"] == "problem_guidance":
            if not ticket["evidence"]:
                if payload is not None:
                    raise bad()
                text, cited = (
                    NO_GUIDANCE_EVIDENCE + "\n" + "\n".join(HINTS.values()),
                    [],
                )
            else:
                expected = (
                    len(ticket["selected_skill"]["definition"]["steps"])
                    if ticket["selected_skill"]
                    else 1
                )
                if not isinstance(payload, list) or len(payload) != expected:
                    raise bad()
                steps = [
                    {"ordinal": index, "text": render_selection(value)}
                    for index, value in enumerate(payload, 1)
                ]
                text, cited = "\n".join(step["text"] for step in steps), []
        elif ticket["evidence"]:
            text, cited = validate_claims(payload, ticket["evidence"])
            text = text or NO_EVIDENCE
        else:
            if payload is not None:
                raise bad()
            text, cited = NO_EVIDENCE, []
        if (
            segments is not None
            and ticket["evidence"]
            and ticket["configuration"]["app_key"] == "material_qa"
        ):
            if not isinstance(segments, list) or not 1 <= len(segments) <= 3:
                raise bad()
            steps = []
            for index, segment in enumerate(segments, 1):
                if not isinstance(segment, dict) or segment.keys() != {
                    "insufficient",
                    "claims",
                    "more",
                }:
                    raise bad()
                step_text, _ = validate_claims(
                    {
                        "insufficient": segment["insufficient"],
                        "claims": segment["claims"],
                    },
                    ticket["evidence"],
                )
                steps.append({"ordinal": index, "text": step_text or NO_EVIDENCE})
            if "\n".join(step["text"] for step in steps) != text:
                raise conflict()
        try:
            self.recheck(identity, cookie, ticket)
            with self.repository.transaction() as connection:
                row = self._ticket(connection, identity, cookie, ticket)
                now = self.ai.clock()
                self.repository.commit_message(
                    connection, identity, ticket, text, cited, now
                )
                self.repository.finish_attempt(
                    connection,
                    ticket,
                    status="succeeded",
                    details={"text": text, "steps": steps},
                    duration_ms=round((time.monotonic() - ticket["started"]) * 1000),
                    now=now,
                )
                return {
                    "message_id": ticket["message_id"],
                    "run_id": ticket["run_id"],
                    "citations": cited,
                    "operation_id": row["id"],
                }
        except self.ai.database_error:
            raise unavailable() from None

    def abort(self, identity, ticket, *, code=1500):
        if code not in (1000, 1100, 1200, 1300, 1400, 1500, 1501, 1600):
            code = 1500
        try:
            with self.repository.transaction() as connection:
                row = self.repository.lock_session_operation(
                    connection,
                    identity,
                    ticket["session_id"],
                    operation_id=ticket["operation_id"],
                )
                if (
                    row is not None
                    and row["status"] == "running"
                    and row["lease_token"] == ticket["token"]
                ):
                    self.repository.finish_attempt(
                        connection,
                        ticket,
                        status="interrupted",
                        error_code=code,
                        now=self.ai.clock(),
                    )
        except self.ai.database_error:
            raise unavailable() from None
