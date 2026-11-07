"""课程对话网关：有限预算、JSON 结构、无工具、无原文日志。"""

import json
import time

from app.adapters.index_clients import IndexDependencyError, JsonEndpoint, remaining


class ChatProtocolError(IndexDependencyError):
    pass


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_key")
        result[key] = value
    return result


class ChatClient:
    def __init__(self, config, *, endpoint=None, sleep=time.sleep, on_result=None):
        self.config = config
        self.endpoint = endpoint or JsonEndpoint(
            config.base_url, {"Authorization": "Bearer " + config.api_key}
        )
        self.sleep = sleep
        self.on_result = on_result or (lambda **details: None)

    def complete(self, messages, deadline, *, before_call=None):
        if not self.config.api_key:
            raise IndexDependencyError("chat_config")
        started = time.monotonic()
        for attempt in range(2):
            remaining(deadline)
            if before_call:
                before_call()
            try:
                result = self.endpoint.request(
                    "POST",
                    "/chat/completions",
                    {
                        "model": self.config.model,
                        "messages": messages,
                        "temperature": self.config.temperature,
                        "max_tokens": self.config.max_output_tokens,
                        "response_format": {"type": "json_object"},
                    },
                    deadline,
                )
                break
            except IndexDependencyError as error:
                if not error.transient or attempt or remaining(deadline) <= 1:
                    raise
                self.sleep(1)
        try:
            choices = result["choices"]
            if not isinstance(choices, list) or len(choices) != 1:
                raise ValueError
            if choices[0].get("finish_reason") not in (None, "stop"):
                raise ValueError
            if "model" in result and result["model"] != self.config.model:
                raise ValueError
            message = choices[0]["message"]
            if (
                message.get("role", "assistant") != "assistant"
                or message.get("tool_calls") not in (None, [])
                or message.get("function_call") is not None
            ):
                raise ValueError
            content = message["content"]
            if not isinstance(content, str) or not 1 <= len(content) <= 12000:
                raise ValueError
            payload = json.loads(content, object_pairs_hook=unique_object)
        except (KeyError, TypeError, ValueError, AttributeError):
            raise ChatProtocolError("chat_structure") from None
        usage = result.get("usage", {})
        tokens = (
            {
                key: value
                for key, value in usage.items()
                if key in ("prompt_tokens", "completion_tokens", "total_tokens")
                and type(value) is int
                and 0 <= value <= 10_000_000
            }
            if isinstance(usage, dict)
            else {}
        )
        self.on_result(
            stage="chat",
            model=self.config.model,
            model_config=self.config.version,
            response_model_present="model" in result,
            duration_ms=round((time.monotonic() - started) * 1000, 2),
            **tokens,
        )
        return payload
