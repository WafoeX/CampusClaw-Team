"""班级配置与三类同步应用；本人记录、短事务和有界模型调用。"""

import time
from datetime import timedelta
from uuid import uuid4

from app.services.access import AccessDenied
from app.services.ai_contracts import (
    AI_CONFIGURE,
    APPS,
    DEFAULT_ROLE,
    PROMPT_VERSION,
    bad,
    configuration_input,
    conflict,
    fingerprint,
    render_prompt,
    revision,
    run_messages,
    validate_output,
    variables,
)
from app.services.auth import digest_cookie, invalid_session, utc_now
from app.services.materials import missing, unavailable


def configuration_view(row, kind, *, detail=False):
    keys = ["id", "name", "revision", "enabled"] + (
        ["app_key"] if kind == "template" else []
    )
    result = {key: row[key] for key in keys}
    if detail:
        result["prompt"] = row["prompt"]
        if kind == "assistant":
            result.update(
                material_ids=row["material_ids"],
                skill_ids=row["skill_ids"],
                uses_default_role=not row["prompt"],
                effective_prompt=row["prompt"] or DEFAULT_ROLE,
            )
    return result


def run_view(row, *, detail=True, now=None):
    result = {
        key: row[key]
        for key in (
            "id",
            "app_key",
            "attempt",
            "status",
            "configuration",
            "error_code",
            "duration_ms",
        )
    }
    if (
        row["status"] == "running"
        and row.get("lease_expires_at") is not None
        and row["lease_expires_at"] <= (now or utc_now())
    ):
        result.update(status="interrupted", error_code=1500)
    if row.get("session_id") is not None:
        result["session_id"] = row["session_id"]
    result["created_at"] = row["created_at"].isoformat() + "Z"
    if detail:
        result.update(
            input=row["input_payload"] if row["status"] == "succeeded" else None,
            result=row["details"] if row["status"] == "succeeded" else None,
        )
    return result


class AIApplicationService:
    def __init__(
        self,
        repository,
        database_error,
        chat,
        dependency_error,
        protocol_error,
        *,
        capacity,
        model_guard,
        quota,
        expires_at=None,
        model_configuration=None,
        clock=utc_now,
    ):
        self.repository = repository
        self.database_error = database_error
        self.chat = chat
        self.dependency_error = dependency_error
        self.protocol_error = protocol_error
        self.capacity = capacity
        self.model_guard = model_guard
        self.quota = quota
        self.expires_at = expires_at
        self.model_configuration = model_configuration or {}
        self.clock = clock

    def _actor(self, connection, identity, cookie, *, teacher=False):
        digest = digest_cookie(cookie)
        actor = (
            self.repository.lock_actor(
                connection, identity.subject_id, digest, self.clock
            )
            if digest
            else None
        )
        if actor is None:
            raise invalid_session()
        if actor.class_id != identity.class_id or actor.role not in (
            "teacher",
            "student",
        ):
            raise missing()
        if teacher and actor.role != "teacher":
            raise AccessDenied(403, 1200, "当前账号无此操作权限")
        return actor

    def _configuration(self, connection, identity, kind, resource_id, *, teacher):
        row = self.repository.lock_configuration(
            connection, kind, identity.class_id, resource_id
        )
        if row is None or (not teacher and not row["enabled"]):
            raise missing()
        return row

    def catalogue(self, identity):
        try:
            skill_options = (
                self.repository.bindable_skills(identity.class_id)
                if AI_CONFIGURE in identity.permissions
                else []
            )
            rows, _ = self.repository.configurations(
                "template", identity.class_id, 1, 100, teacher=False
            )
        except self.database_error:
            raise unavailable() from None
        return {
            "bindable_skills": [dict(row) for row in skill_options],
            "items": [
                {
                    "key": key,
                    "name": name,
                    "url": "/ask" if key == "material_qa" else "/apps",
                    "templates": [
                        configuration_view(row, "template")
                        for row in rows
                        if row["app_key"] == key
                    ],
                }
                for key, name in APPS.items()
            ],
        }

    def list_configurations(self, identity, kind, page, page_size, app_key=None):
        if app_key is not None and (kind != "template" or app_key not in APPS):
            raise bad("应用筛选无效")
        try:
            rows, total = self.repository.configurations(
                kind,
                identity.class_id,
                page,
                page_size,
                teacher=AI_CONFIGURE in identity.permissions,
                app_key=app_key,
            )
        except self.database_error:
            raise unavailable() from None
        return {
            "items": [configuration_view(row, kind) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def read_configuration(self, identity, cookie, kind, resource_id):
        try:
            with self.repository.transaction() as connection:
                actor = self._actor(connection, identity, cookie)
                row = self._configuration(
                    connection,
                    identity,
                    kind,
                    resource_id,
                    teacher=actor.role == "teacher",
                )
                return configuration_view(
                    row, kind, detail=kind == "template" or actor.role == "teacher"
                )
        except self.database_error:
            raise unavailable() from None

    def save_configuration(
        self, identity, cookie, kind, payload, *, key=None, resource_id=None
    ):
        fields = configuration_input(kind, payload, update=resource_id is not None)
        expected = fields.pop("revision", None)
        try:
            with self.repository.transaction() as connection:
                self._actor(connection, identity, cookie, teacher=True)
                now = self.clock()
                if resource_id is None:
                    prior = self.repository.lock_creation(
                        connection, identity.class_id, identity.subject_id, kind, key
                    )
                    if prior is not None:
                        if prior["expires_at"] > now:
                            if prior["fingerprint"] != fingerprint(fields):
                                raise conflict("创建标识已使用，请核对输入")
                            row = self._configuration(
                                connection,
                                identity,
                                kind,
                                prior["resource_id"],
                                teacher=True,
                            )
                            return configuration_view(row, kind, detail=True)
                        self.repository.discard_creation(
                            connection,
                            identity.class_id,
                            identity.subject_id,
                            kind,
                            key,
                        )
                    identifier = str(uuid4())
                    parent = dict(
                        id=identifier,
                        class_id=identity.class_id,
                        creator_id=identity.subject_id,
                        created_at=now,
                        updated_at=now,
                        revision=1,
                    )
                    event = "create"
                else:
                    current = self._configuration(
                        connection, identity, kind, resource_id, teacher=True
                    )
                    if current["revision"] != expected:
                        raise conflict()
                    identifier = resource_id
                    parent = {
                        name: current[name]
                        for name in ("id", "class_id", "creator_id", "created_at")
                    }
                    parent.update(updated_at=now, revision=expected + 1)
                    event = "update" if fields["enabled"] else "disable"
                if kind == "assistant" and not self.repository.bindings_exist(
                    connection,
                    identity.class_id,
                    fields["material_ids"],
                    fields["skill_ids"],
                ):
                    raise missing()
                parent.update(
                    {
                        name: value
                        for name, value in fields.items()
                        if name not in ("prompt", "material_ids", "skill_ids")
                    }
                )
                self.repository.store_configuration(
                    connection,
                    kind,
                    parent,
                    fields["prompt"],
                    identity.subject_id,
                    new=resource_id is None,
                    event=event,
                    material_ids=fields.get("material_ids", ()),
                    skill_ids=fields.get("skill_ids", ()),
                )
                if resource_id is None:
                    self.repository.save_creation(
                        connection,
                        dict(
                            class_id=identity.class_id,
                            actor_id=identity.subject_id,
                            resource_type=kind,
                            request_key=key,
                            fingerprint=fingerprint(fields),
                            resource_id=identifier,
                            created_at=now,
                            expires_at=now + timedelta(hours=24),
                        ),
                        now,
                    )
                row = self.repository.lock_configuration(
                    connection, kind, identity.class_id, identifier
                )
                return configuration_view(row, kind, detail=True)
        except self.database_error:
            raise unavailable() from None

    def delete_template(self, identity, cookie, resource_id, expected):
        revision(expected)
        try:
            with self.repository.transaction() as connection:
                self._actor(connection, identity, cookie, teacher=True)
                row = self._configuration(
                    connection, identity, "template", resource_id, teacher=True
                )
                if row["revision"] != expected:
                    raise conflict()
                parent = {
                    name: row[name]
                    for name in (
                        "id",
                        "class_id",
                        "creator_id",
                        "name",
                        "app_key",
                        "created_at",
                    )
                }
                parent.update(
                    revision=expected + 1,
                    enabled=False,
                    deleted=True,
                    updated_at=self.clock(),
                )
                self.repository.store_configuration(
                    connection,
                    "template",
                    parent,
                    row["prompt"],
                    identity.subject_id,
                    event="delete",
                )
            return {"id": resource_id, "deleted": True}
        except self.database_error:
            raise unavailable() from None

    def preview(self, identity, cookie, resource_id, expected, values):
        values = variables(values)
        revision(expected)
        try:
            with self.repository.transaction() as connection:
                actor = self._actor(connection, identity, cookie)
                row = self._configuration(
                    connection,
                    identity,
                    "template",
                    resource_id,
                    teacher=actor.role == "teacher",
                )
                if row["revision"] != expected:
                    raise conflict()
                return {
                    "template_id": resource_id,
                    "revision": expected,
                    "text": render_prompt(row["prompt"], values),
                }
        except self.database_error:
            raise unavailable() from None

    def _replay(self, identity, cookie, app_key, key, template_id, expected, values):
        with self.repository.transaction() as connection:
            self._actor(connection, identity, cookie)
            prior = self.repository.lock_operation(connection, identity, app_key, key)
            if prior is None:
                return None
            now = self.clock()
            if (
                prior["fingerprint"]
                != fingerprint(
                    {
                        "template_id": template_id,
                        "revision": expected,
                        "variables": values,
                    }
                )
                or prior["expires_at"] <= now
            ):
                raise conflict()
            if prior["status"] == "succeeded":
                row = self.repository.operation_result(
                    connection, identity, prior["id"], now
                )
                if row is None:
                    raise conflict()
                return {"replayed": True, "record": run_view(row)}
            if (
                prior["status"] == "revoked"
                or (prior["status"] == "running" and prior["lease_expires_at"] > now)
                or prior["attempt_count"] >= 3
            ):
                raise conflict("请求仍在执行或已达尝试上限，请查看本人记录")
            return None

    def _admit(self, identity, cookie, app_key, key, template_id, expected, values):
        normalized = {
            "template_id": template_id,
            "revision": expected,
            "variables": values,
        }
        digest = fingerprint(normalized)
        with self.repository.transaction() as connection:
            self._actor(connection, identity, cookie)
            now = self.clock()
            prior = self.repository.lock_operation(connection, identity, app_key, key)
            if prior is not None:
                if prior["fingerprint"] != digest or prior["expires_at"] <= now:
                    raise conflict()
                if prior["status"] == "succeeded":
                    result = self.repository.operation_result(
                        connection, identity, prior["id"], now
                    )
                    if result is None:
                        raise conflict()
                    return {"replayed": True, "record": run_view(result)}
                if (
                    prior["status"] == "revoked"
                    or (
                        prior["status"] == "running" and prior["lease_expires_at"] > now
                    )
                    or prior["attempt_count"] >= 3
                ):
                    raise conflict("请求仍在执行或已达尝试上限，请查看本人记录")
                if prior["status"] == "running":
                    previous = self.repository.current_attempt(
                        connection, prior["id"], prior["attempt_count"]
                    )
                    self.repository.finish_attempt(
                        connection,
                        {"operation_id": prior["id"], "run_id": previous["id"]},
                        status="interrupted",
                        error_code=1500,
                        now=now,
                    )
            template = self._configuration(
                connection, identity, "template", template_id, teacher=False
            )
            if template["revision"] != expected or template["app_key"] != app_key:
                raise conflict()
            rendered = render_prompt(template["prompt"], values)
            attempt = prior["attempt_count"] + 1 if prior else 1
            operation_id = prior["id"] if prior else str(uuid4())
            run_id, token = str(uuid4()), str(uuid4())
            expiry = (
                min(prior["expires_at"], self.expires_at) if prior else self.expires_at
            )
            configuration = self.model_configuration | {
                "app_key": app_key,
                "template_id": template_id,
                "template_revision": expected,
                "prompt_version": PROMPT_VERSION,
            }
            operation = dict(
                id=operation_id,
                class_id=identity.class_id,
                owner_id=identity.subject_id,
                session_id=None,
                app_key=app_key,
                operation_scope=app_key.encode(),
                request_key=key,
                fingerprint=digest,
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
                configuration=configuration,
                details=None,
                created_at=now,
                updated_at=now,
                expires_at=expiry,
            )
            self.repository.insert_attempt(
                connection, operation, run, new=prior is None
            )
            return dict(
                operation_id=operation_id,
                run_id=run_id,
                token=token,
                attempt=attempt,
                template_id=template_id,
                revision=expected,
                prompt=template["prompt"],
                rendered_prompt=rendered,
            )

    def _finish(self, identity, cookie, ticket, text, duration_ms):
        with self.repository.transaction() as connection:
            self._actor(connection, identity, cookie)
            row = self.repository.lock_ticket(connection, identity, ticket)
            now = self.clock()
            if (
                row is None
                or row["status"] != "running"
                or row["lease_token"] != ticket["token"]
                or row["lease_expires_at"] <= now
                or row["expires_at"] <= now
            ):
                raise conflict()
            template = self._configuration(
                connection, identity, "template", ticket["template_id"], teacher=False
            )
            if template["revision"] != ticket["revision"]:
                raise conflict()
            self.repository.finish_attempt(
                connection,
                ticket,
                status="succeeded",
                details={"text": text, "rendered_prompt": ticket["rendered_prompt"]},
                duration_ms=duration_ms,
                now=now,
            )
            return {
                "replayed": False,
                "record": run_view(
                    self.repository.operation_result(
                        connection, identity, ticket["operation_id"], now
                    )
                ),
            }

    def _fail(self, identity, ticket, code, duration_ms):
        with self.repository.transaction() as connection:
            row = self.repository.lock_ticket(connection, identity, ticket)
            if (
                row is not None
                and row["status"] == "running"
                and row["lease_token"] == ticket["token"]
            ):
                self.repository.finish_attempt(
                    connection,
                    ticket,
                    status="failed",
                    error_code=code,
                    duration_ms=duration_ms,
                    now=self.clock(),
                )

    def run(self, identity, cookie, app_key, key, template_id, expected, values):
        if app_key not in APPS or app_key == "material_qa":
            raise bad("请从资料问答入口提问")
        revision(expected)
        values = variables(values)
        try:
            replay = self._replay(
                identity, cookie, app_key, key, template_id, expected, values
            )
        except self.database_error:
            raise unavailable() from None
        if replay is not None:
            return replay
        if (
            self.chat is None
            or self.expires_at is None
            or self.expires_at <= self.clock()
        ):
            raise AccessDenied(
                503, 1500, "执行配置未就绪，请联系教师检查模型与数据到期设置"
            )
        ticket = None
        started = time.monotonic()
        deadline = started + 35
        try:
            with self.capacity.reserve():
                ticket = self._admit(
                    identity, cookie, app_key, key, template_id, expected, values
                )
                if ticket.get("replayed"):
                    return ticket
                with self.model_guard(identity):
                    response = self.chat.complete(
                        run_messages(app_key, ticket["prompt"], values),
                        deadline,
                        before_call=lambda: self.quota(identity),
                    )
                output = validate_output(response)
                if time.monotonic() >= deadline:
                    raise unavailable()
                return self._finish(
                    identity,
                    cookie,
                    ticket,
                    output,
                    round((time.monotonic() - started) * 1000),
                )
        except self.protocol_error:
            error = AccessDenied(502, 1501, "生成结果未通过校验，请重试")
        except (self.database_error, self.dependency_error):
            error = unavailable()
        except AccessDenied as denied:
            error = denied
        if ticket is not None and not ticket.get("replayed"):
            try:
                self._fail(
                    identity,
                    ticket,
                    error.code,
                    round((time.monotonic() - started) * 1000),
                )
            except self.database_error:
                raise unavailable() from None
        raise error from None

    def read_run(self, identity, run_id):
        try:
            row = self.repository.read_run(identity, run_id, self.clock())
        except self.database_error:
            raise unavailable() from None
        if row is None:
            raise missing()
        return run_view(row, now=self.clock())

    def list_runs(self, identity, page, page_size):
        try:
            rows, total = self.repository.list_runs(
                identity, page, page_size, self.clock()
            )
        except self.database_error:
            raise unavailable() from None
        return {
            "items": [run_view(row, detail=False, now=self.clock()) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
