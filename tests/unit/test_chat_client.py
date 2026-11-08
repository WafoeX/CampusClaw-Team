import json
import time
from unittest.mock import Mock

import pytest

from app.adapters.chat_client import ChatClient, ChatProtocolError
from app.config import ChatSettings

CONFIG = ChatSettings(
    "https://ai-gateway.devops.hello1023.com/v1", "synthetic-value", "course-chat"
)


@pytest.mark.parametrize(
    "message",
    [
        {"role": "tool", "content": "{}"},
        {"content": "```json\n{}\n```"},
        {"content": "{}", "tool_calls": [{"name": "unsafe"}]},
        {"content": "{}", "function_call": {}},
        {"content": '{"claims":[],"claims":[1]}'},
        {"content": None},
    ],
)
def test_QA_F05_gateway_protocol_rejects_tools_duplicates_and_nonjson(message):
    endpoint = Mock()
    endpoint.request.return_value = {"choices": [{"message": message}]}
    with pytest.raises(ChatProtocolError):
        ChatClient(CONFIG, endpoint=endpoint).complete([], time.monotonic() + 35)
    assert endpoint.request.call_count == 1


def test_QA_N01_chat_configuration_and_sanitized_usage_only():
    endpoint, logger = Mock(), Mock()
    endpoint.request.return_value = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": json.dumps({"insufficient": True, "claims": []}),
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 5,
            "completion_tokens": 3,
            "total_tokens": 8,
            "input": "private-text",
        },
    }
    result = ChatClient(CONFIG, endpoint=endpoint, on_result=logger).complete(
        [{"role": "system", "content": "system"}], time.monotonic() + 35
    )
    assert result == {"insufficient": True, "claims": []}
    request = endpoint.request.call_args.args[2]
    assert (
        request["model"] == "course-chat"
        and request["temperature"] == 0.2
        and request["max_tokens"] == 2048
    )
    assert "private-text" not in str(logger.call_args) and "synthetic-value" not in str(
        logger.call_args
    )
    assert logger.call_args.kwargs["total_tokens"] == 8


def test_ST_F04_after_first_delta_transient_failure_is_not_automatically_retried():
    from app.adapters.index_clients import IndexDependencyError

    endpoint, quota, sleep = Mock(), Mock(), Mock()
    endpoint.request.side_effect = IndexDependencyError("synthetic", transient=True)
    client = ChatClient(CONFIG, endpoint=endpoint, sleep=sleep)
    with pytest.raises(IndexDependencyError):
        client.complete_once([], time.monotonic() + 35, before_call=quota)
    assert endpoint.request.call_count == 1 and quota.call_count == 1
    sleep.assert_not_called()


def test_ST_F06_cancelled_gateway_is_not_retried_or_charged_again():
    from app.adapters.index_clients import IndexDependencyError
    from app.services.streaming import StreamCancelled, StreamContext

    context = StreamContext(time.monotonic() + 35)
    endpoint, quota, sleep = Mock(), Mock(), Mock()

    def interrupted(*args, **kwargs):
        assert kwargs["context"] is context
        context.cancel()
        raise IndexDependencyError("transport", transient=True)

    endpoint.request.side_effect = interrupted
    with pytest.raises(StreamCancelled):
        ChatClient(CONFIG, endpoint=endpoint, sleep=sleep).complete_cancellable(
            [], context.deadline, context=context, before_call=quota
        )
    assert endpoint.request.call_count == quota.call_count == 1
    sleep.assert_not_called()
