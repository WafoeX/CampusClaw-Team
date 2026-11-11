"""本班工具连接的登记、发现及撤销。"""

import re
import threading
import time
from contextlib import contextmanager
from uuid import uuid4

from app.services.ai_contracts import bad, conflict, fingerprint
from app.services.materials import missing, unavailable

ALIAS = re.compile(r"[a-z][a-z0-9-]{0,62}")
NAME = re.compile(r"[a-z][a-z0-9_]{0,63}")
FINGERPRINT = re.compile(r"[a-f0-9]{64}")
REFERENCE = re.compile(r"[a-z][a-z0-9_]{0,63}@[a-z][a-z0-9-]{0,62}")


def matches(pattern, value):
    return isinstance(value, str) and bool(pattern.fullmatch(value))


def references(value):
    if (
        not isinstance(value, list)
        or len(value) > 16
        or not all(matches(REFERENCE, item) for item in value)
        or len(set(value)) != len(value)
    ):
        raise bad("请选择有效且不重复的班级工具")
    return sorted(value)


class ToolConnectors:
    def __init__(
        self, ai, repository, directory, protocol, dependency_error, integrity_error
    ):
        self.ai = ai
        self.repository = repository
        self.directory = directory
        self.protocol = protocol
        self.dependency_error = dependency_error
        self.integrity_error = integrity_error
        self.sessions = {}
        self.active_calls = {}
        self.lock = threading.Lock()

    @contextmanager
    def use_connection(self, connector, context):
        key = (connector["id"], connector["generation"])
        with self.lock:
            if key not in self.sessions:
                raise self.dependency_error("revoked")
            session = self.sessions[key]
            active = ActiveToolCall(context, self.dependency_error)
            self.active_calls.setdefault(key, set()).add(active)
        try:
            yield session, active
        finally:
            with self.lock:
                tracked = self.active_calls.get(key)
                if tracked:
                    tracked.discard(active)
                    if not tracked:
                        self.active_calls.pop(key)

    def _withdraw(self, resource_id, generation):
        key = (resource_id, generation)
        for call in self.active_calls.pop(key, ()):
            call.cancel()
        return self.sessions.pop(key, None)

    @contextmanager
    def transaction(self, identity, cookie):
        try:
            with self.ai.repository.transaction() as connection:
                self.ai._actor(connection, identity, cookie, teacher=True)
                yield connection
        except self.integrity_error:
            raise conflict("同班已有此服务别名") from None
        except self.ai.database_error:
            raise unavailable() from None

    def options(self, identity, cookie):
        with self.transaction(identity, cookie):
            return [
                {
                    "key": target.key,
                    "label": target.label,
                    "protocol": target.protocol,
                    "credential_configured": bool(target.token),
                }
                for target in self.directory.values()
            ]

    def _target(self, row):
        target = self.directory.get(row["directory_key"])
        if target is None or target.version != row["directory_version"]:
            return None
        return target

    def resolve(self, connection, identity, reference):
        name, alias = reference.split("@")
        row = self.repository.reference(connection, identity.class_id, alias, name)
        if row is None:
            return None, None
        target = self._target(row)
        policy = target.tools.get(name) if target else None
        if (
            policy is None
            or row["deleted_at"] is not None
            or row["status"] != "connected"
            or row["generation"] != row["tool_generation"]
            or not row["enabled"]
            or not row["definition"]
            or row["definition"]["inputSchema"] != policy.definition["inputSchema"]
            or (row["id"], row["generation"]) not in self.sessions
        ):
            return row, None
        return row, policy

    def validate_binding(self, connection, identity, refs):
        for reference in refs:
            row, policy = self.resolve(connection, identity, reference)
            if row is None or (row["name"] is None and not row["previously_approved"]):
                raise missing()
            if policy is None:
                raise conflict("工具尚未启用或连接不可用")

    def candidates(self, connection, identity, selected, mode, *, practice=None):
        result = {}
        for reference in selected:
            row, policy = self.resolve(connection, identity, reference)
            if policy is None or mode not in policy.modes:
                continue
            if row["name"] == "unit_convert" and practice is None:
                continue
            result[reference] = {"row": row, "policy": policy}
        return result

    def view(self, row):
        target = self._target(row)
        connected = row["status"]
        if (
            connected == "connected"
            and (row["id"], row["generation"]) not in self.sessions
        ):
            connected = "unavailable"
        return {
            "id": row["id"],
            "alias": row["alias"],
            "status": connected,
            "label": target.label if target else None,
            "credential_configured": bool(target and target.token),
            "created_at": row["created_at"].isoformat() + "Z",
        }

    def register(self, identity, cookie, payload):
        if (
            not isinstance(payload, dict)
            or payload.keys() != {"alias", "key"}
            or not matches(ALIAS, payload["alias"])
            or not matches(ALIAS, payload["key"])
            or payload["key"] not in self.directory
        ):
            raise bad("请选择批准的服务并输入有效别名")
        target = self.directory[payload["key"]]
        with self.transaction(identity, cookie):
            pass
        try:
            self.protocol.wire.addresses(target, time.monotonic() + 2)
        except self.dependency_error:
            raise unavailable() from None
        now = self.ai.clock()
        row = {
            "id": str(uuid4()),
            "class_id": identity.class_id,
            "creator_id": identity.subject_id,
            "alias": payload["alias"],
            "directory_key": target.key,
            "directory_version": target.version,
            "generation": 0,
            "status": "disconnected",
            "created_at": now,
            "updated_at": now,
        }
        with self.transaction(identity, cookie) as connection:
            self.repository.create(connection, row)
        return self.view(row)

    def list(self, identity, cookie, page, size):
        with self.transaction(identity, cookie) as connection:
            items, total = self.repository.list(
                connection, identity.class_id, page, size
            )
            return {
                "items": [self.view(row) for row in items],
                "total": total,
                "page": page,
                "page_size": size,
            }

    def audit(self, identity, cookie, page, size):
        with self.transaction(identity, cookie) as connection:
            rows, total = self.repository.audit(
                connection, identity.class_id, self.ai.clock(), page, size
            )
        items = [
            {
                "tool": f"{row['tool_name']}@{row['alias']}"
                if row["tool_name"]
                else None,
                "outcome": row["outcome"],
                "reason": row["reason"],
                "duration_ms": row["duration_ms"],
                "created_at": row["created_at"].isoformat() + "Z",
            }
            for row in rows
        ]
        return {"items": items, "total": total, "page": page, "page_size": size}

    def _connector(self, connection, identity, resource_id, *, lock=False):
        row = self.repository.connector(
            connection, identity.class_id, resource_id, lock=lock
        )
        if row is None:
            raise missing()
        return row

    def read(self, identity, cookie, resource_id):
        with self.transaction(identity, cookie) as connection:
            return self.view(self._connector(connection, identity, resource_id))

    def _close(self, target, session):
        if target is not None and session:
            self.protocol.close(target, session, time.monotonic() + 1)

    def connect(self, identity, cookie, resource_id):
        with self.lock:
            with self.transaction(identity, cookie) as connection:
                row = self._connector(connection, identity, resource_id, lock=True)
                target = self._target(row)
                if target is None:
                    raise unavailable()
                generation = row["generation"] + 1
                self.repository.set_state(
                    connection,
                    row,
                    status="connecting",
                    generation=generation,
                    updated_at=self.ai.clock(),
                )
            previous = self._withdraw(resource_id, row["generation"])
        self._close(target, previous)
        session = None
        connected = False
        try:
            try:
                session, catalog = self.protocol.discover(target, time.monotonic() + 8)
            except self.dependency_error:
                catalog = None
            with self.lock:
                with self.transaction(identity, cookie) as connection:
                    current = self._connector(
                        connection, identity, resource_id, lock=True
                    )
                    if (
                        current["generation"] != generation
                        or current["status"] != "connecting"
                    ):
                        raise conflict("连接状态已变化，请刷新后重试")
                    if catalog is None:
                        self.repository.set_state(
                            connection,
                            current,
                            status="disconnected",
                            updated_at=self.ai.clock(),
                        )
                    else:
                        self._publish(connection, current, target, catalog)
                if catalog is not None:
                    self.sessions[resource_id, generation] = session
                    connected = True
            if catalog is None:
                raise unavailable()
            return self.view(dict(current) | {"status": "connected"})
        finally:
            if not connected:
                self._close(target, session)

    def _publish(self, connection, connector, target, catalog):
        previous = {
            row["name"]: row for row in self.repository.discovery(connection, connector)
        }
        rows = []
        for item in catalog:
            name = item["name"]
            digest = fingerprint(item).hex()
            before = previous.get(name)
            approved = bool(
                before and before["fingerprint"] == digest and before["approved"]
            )
            policy = target.tools.get(name)
            allowed = policy and policy.definition["inputSchema"] == item["inputSchema"]
            rows.append(
                {
                    "class_id": connector["class_id"],
                    "connector_id": connector["id"],
                    "generation": connector["generation"],
                    "name": name,
                    "definition": item,
                    "fingerprint": digest,
                    "approved": approved,
                    "enabled": bool(approved and allowed and before["enabled"]),
                }
            )
        self.repository.replace_discovery(connection, connector, rows)
        self.repository.set_state(
            connection, connector, status="connected", updated_at=self.ai.clock()
        )

    def disconnect(self, identity, cookie, resource_id, *, remove=False):
        with self.lock:
            with self.transaction(identity, cookie) as connection:
                row = self._connector(connection, identity, resource_id, lock=True)
                if row["status"] == "disconnected" and not remove:
                    return self.view(row)
                now = self.ai.clock()
                changes = {
                    "status": "disconnected",
                    "generation": row["generation"] + 1,
                    "updated_at": now,
                }
                if remove:
                    changes["deleted_at"] = now
                    self.repository.replace_discovery(connection, row, [])
                self.repository.set_state(connection, row, **changes)
            session = self._withdraw(resource_id, row["generation"])
        self._close(self._target(row), session)
        return self.view(dict(row) | changes)

    def _tool_view(self, connector, row):
        target = self._target(connector)
        policy = target.tools.get(row["name"]) if target else None
        return {
            "name": row["name"],
            "description": row["definition"]["description"],
            "inputSchema": row["definition"]["inputSchema"],
            "fingerprint": row["fingerprint"],
            "approved": row["approved"],
            "enabled": row["enabled"],
            "allowed": bool(
                policy
                and policy.definition["inputSchema"] == row["definition"]["inputSchema"]
            ),
        }

    def tools(self, identity, cookie, resource_id):
        with self.transaction(identity, cookie) as connection:
            row = self._connector(connection, identity, resource_id)
            if self.view(row)["status"] != "connected":
                return []
            return [
                self._tool_view(row, item)
                for item in self.repository.discovery(connection, row)
            ]

    def review(self, identity, cookie, resource_id, name, payload):
        if (
            not matches(NAME, name)
            or not isinstance(payload, dict)
            or payload.keys() != {"fingerprint", "enabled"}
            or not matches(FINGERPRINT, payload["fingerprint"])
            or type(payload["enabled"]) is not bool
        ):
            raise bad()
        with self.lock, self.transaction(identity, cookie) as connection:
            connector = self._connector(connection, identity, resource_id, lock=True)
            if self.view(connector)["status"] != "connected":
                raise conflict("连接不可用，请重新连接后审阅")
            row = next(
                (
                    item
                    for item in self.repository.discovery(connection, connector)
                    if item["name"] == name
                ),
                None,
            )
            if row is None:
                raise missing()
            view = self._tool_view(connector, row)
            if row["fingerprint"] != payload["fingerprint"]:
                raise conflict("工具定义已变化，请重新审阅")
            enabled = payload["enabled"]
            if enabled and not view["allowed"]:
                raise conflict("部署未批准启用此工具")
            if view["approved"] and view["enabled"] == enabled:
                return view
            event = {
                key: row[key]
                for key in (
                    "class_id",
                    "connector_id",
                    "name",
                    "generation",
                    "fingerprint",
                    "definition",
                )
            }
            event.update(
                id=str(uuid4()),
                teacher_id=identity.subject_id,
                enabled=enabled,
                created_at=self.ai.clock(),
            )
            self.repository.review(connection, row, event)
            return view | {"approved": True, "enabled": enabled}


class ActiveToolCall:
    def __init__(self, stream, dependency_error):
        self.stream = stream
        self.dependency_error = dependency_error
        self.revoked = threading.Event()
        self.callbacks = []
        self.lock = threading.Lock()

    def check(self):
        self.stream.check()
        if self.revoked.is_set():
            raise self.dependency_error("revoked")

    def on_cancel(self, callback):
        self.stream.on_cancel(callback)
        with self.lock:
            if self.revoked.is_set():
                callback()
            else:
                self.callbacks.append(callback)

    def cancel(self):
        with self.lock:
            self.revoked.set()
            for callback in self.callbacks:
                callback()
            self.callbacks.clear()
