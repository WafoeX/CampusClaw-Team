"""固定版本 MCP Streamable HTTP 客户端与只读 HTTP 适配。"""

import json
import re
from uuid import uuid4

from app.adapters.chat_client import unique_object
from app.adapters.tool_transport import MAX_RESPONSE, ToolDependencyError

PROTOCOL = "2025-06-18"
MAX_PAGES = 4
MAX_TOOLS = 32
SESSION_ID = re.compile(r"[!-~]{1,160}")


def invalid_constant(_value):
    raise ValueError


def parse_json(body):
    try:
        value = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=invalid_constant,
        )
        if not isinstance(value, dict):
            raise ValueError
        return value
    except (ValueError, RecursionError):
        raise ToolDependencyError("response") from None


def sse_message(body, request_id):
    message = None
    events = bytes(body).replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    for event in events.split(b"\n\n")[:-1]:
        lines = [
            line[5:].removeprefix(b" ")
            for line in event.split(b"\n")
            if line.startswith(b"data:")
        ]
        if not lines:
            continue
        parsed = parse_json(b"\n".join(lines))
        if parsed.get("jsonrpc") != "2.0":
            raise ToolDependencyError("response")
        if parsed.get("id") == request_id:
            if message is not None:
                raise ToolDependencyError("response")
            message = parsed
    return message


def matching_response(media, body, request_id):
    if media == "application/json":
        message = parse_json(body)
    elif media == "text/event-stream":
        message = sse_message(body, request_id)
        if message is None:
            raise ToolDependencyError("response")
    else:
        raise ToolDependencyError("response")
    if (
        message.get("id") != request_id
        or message.get("jsonrpc") != "2.0"
        or set(message) != {"jsonrpc", "id", "result"}
        or not isinstance(message.get("result"), dict)
    ):
        raise ToolDependencyError("response")
    return message["result"]


class ToolProtocol:
    def __init__(self, wire):
        self.wire = wire

    def _rpc(
        self, target, method, deadline, *, session=None, params=None, context=None
    ):
        if target.credential_required and not target.token:
            raise ToolDependencyError("credential")
        message = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        if method != "notifications/initialized":
            message["id"] = uuid4().hex
        headers = {
            **target.headers(),
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if method != "initialize":
            headers["MCP-Protocol-Version"] = PROTOCOL
            if session:
                headers["Mcp-Session-Id"] = session

        def stop(response_headers, data):
            return (
                response_headers.get_content_type() == "text/event-stream"
                and "id" in message
                and sse_message(data, message["id"]) is not None
            )

        status, response_headers, body = self.wire.request(
            target,
            "POST",
            target.path,
            deadline,
            headers=headers,
            body=json.dumps(message, allow_nan=False).encode(),
            context=context,
            stop=stop,
        )
        response_headers = {
            key.lower(): value for key, value in response_headers.items()
        }
        if "id" not in message:
            if status != 202 or body:
                raise ToolDependencyError("response")
            return None, response_headers, 0
        media = (
            response_headers.get("content-type", "").partition(";")[0].strip().lower()
        )
        return (
            matching_response(media, body, message["id"]),
            response_headers,
            len(body),
        )

    def discover(self, target, deadline):
        if target.credential_required and not target.token:
            raise ToolDependencyError("credential")
        if target.protocol == "http":
            self.wire.addresses(target, deadline)
            return None, [policy.definition for policy in target.tools.values()]
        result, headers, _ = self._rpc(
            target,
            "initialize",
            deadline,
            params={
                "protocolVersion": PROTOCOL,
                "capabilities": {},
                "clientInfo": {"name": "campusclaw", "version": "1"},
            },
        )
        session = headers.get("mcp-session-id")
        capabilities = result.get("capabilities")
        if (
            result.get("protocolVersion") != PROTOCOL
            or not isinstance(capabilities, dict)
            or not isinstance(capabilities.get("tools"), dict)
            or (session is not None and not SESSION_ID.fullmatch(session))
        ):
            raise ToolDependencyError("protocol")
        try:
            self._rpc(target, "notifications/initialized", deadline, session=session)
            return session, self._list(target, session, deadline)
        except ToolDependencyError:
            self.close(target, session, deadline)
            raise

    def _list(self, target, session, deadline):
        catalog, seen, cursors = [], set(), set()
        cursor, size = None, 0
        for _ in range(MAX_PAGES):
            reply, _, amount = self._rpc(
                target,
                "tools/list",
                deadline,
                session=session,
                params={"cursor": cursor} if cursor else None,
            )
            size += amount
            tools = reply.get("tools")
            if (
                not isinstance(tools, list)
                or len(catalog) + len(tools) > MAX_TOOLS
                or size > MAX_RESPONSE
            ):
                raise ToolDependencyError("response")
            for item in tools:
                if not isinstance(item, dict):
                    raise ToolDependencyError("response")
                if target.token and target.token in json.dumps(
                    item, ensure_ascii=False
                ):
                    raise ToolDependencyError("response")
                name = item.get("name")
                description = item.get("description", "")
                schema = item.get("inputSchema")
                if (
                    not isinstance(name, str)
                    or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", name)
                    or name in seen
                    or not isinstance(description, str)
                    or len(description) > 1000
                    or not isinstance(schema, dict)
                    or schema.get("type") != "object"
                ):
                    raise ToolDependencyError("response")
                seen.add(name)
                catalog.append(
                    {"name": name, "description": description, "inputSchema": schema}
                )
            cursor = reply.get("nextCursor")
            if cursor is None:
                return catalog
            if (
                not isinstance(cursor, str)
                or not 1 <= len(cursor) <= 256
                or cursor in cursors
            ):
                raise ToolDependencyError("response")
            cursors.add(cursor)
        raise ToolDependencyError("response")

    def close(self, target, session, deadline):
        if target.protocol != "mcp" or not session:
            return
        try:
            self.wire.request(
                target,
                "DELETE",
                target.path,
                deadline,
                headers={
                    **target.headers(),
                    "MCP-Protocol-Version": PROTOCOL,
                    "Mcp-Session-Id": session,
                },
            )
        except ToolDependencyError:
            pass

    def call(self, target, session, name, arguments, deadline, *, context=None):
        if target.credential_required and not target.token:
            raise ToolDependencyError("credential")
        policy = target.tools.get(name)
        if policy is None or not policy.accepts(arguments):
            raise ToolDependencyError("arguments")
        if target.protocol == "http":
            _, headers, body = self.wire.request(
                target,
                "GET",
                policy.path,
                deadline,
                headers={**target.headers(), "Accept": "application/json"},
                query=arguments,
                context=context,
            )
            headers = {key.lower(): value for key, value in headers.items()}
            media = headers.get("content-type", "").partition(";")[0].strip().lower()
            if media != "application/json":
                raise ToolDependencyError("response")
            result = parse_json(body)
        else:
            result, _, _ = self._rpc(
                target,
                "tools/call",
                deadline,
                session=session,
                params={"name": name, "arguments": arguments},
                context=context,
            )
            blocks = result.get("content")
            if (
                set(result) - {"content", "isError"}
                or result.get("isError", False) is not False
                or not isinstance(blocks, list)
                or len(blocks) != 1
                or not isinstance(blocks[0], dict)
                or set(blocks[0]) != {"type", "text"}
                or blocks[0]["type"] != "text"
                or not isinstance(blocks[0]["text"], str)
            ):
                raise ToolDependencyError("response")
            result = parse_json(blocks[0]["text"].encode())
        if not policy.accepts_result(result):
            raise ToolDependencyError("response")
        return result
