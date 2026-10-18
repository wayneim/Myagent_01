"""Exercise real SDK message models with mocked network calls for both adapters."""

from copy import deepcopy
from dataclasses import asdict
import json
from unittest.mock import patch

import httpx
import pytest
from anthropic.types import Message as AnthropicMessage
from openai.types.chat import ChatCompletion

from myagent.protocol import AssistantTurn, ToolCall, ToolResult, ToolResultsMessage, UserMessage
from myagent.provider import ProviderError
from myagent.providers.minimax import MiniMaxProvider
from myagent.providers.qwen import QwenProvider


@pytest.fixture(params=["minimax", "qwen"])
def adapter(request):
    name = request.param
    factory = "myagent.providers.minimax.Anthropic" if name == "minimax" else "myagent.providers.qwen.OpenAI"
    cls = MiniMaxProvider if name == "minimax" else QwenProvider
    with patch(factory) as client:
        provider = cls("fixture-key", "http://localhost", "fixture-model")
        create = client.return_value.messages.create if name == "minimax" else client.return_value.chat.completions.create

        def response(calls=(), text="fixture answer"):
            if name == "minimax":
                return AnthropicMessage.model_validate({
                    "id": "msg_fixture", "type": "message", "role": "assistant", "model": "fixture-model",
                    "stop_reason": "tool_use" if calls else "end_turn", "usage": {"input_tokens": 1, "output_tokens": 1},
                    "content": [{"type": "thinking", "thinking": "opaque fixture", "signature": "fixture-signature"},
                                {"type": "text", "text": text}, *[
                                    {"type": "tool_use", "id": call.call_id, "name": call.name, "input": call.arguments} for call in calls
                                ]],
                })
            return ChatCompletion.model_validate({
                "id": "cmpl_fixture", "created": 0, "object": "chat.completion", "model": "fixture-model",
                "choices": [{"index": 0, "finish_reason": "tool_calls" if calls else "stop", "message": {
                    "role": "assistant", "content": text, "reasoning_content": "opaque fixture",
                    "tool_calls": [{"id": call.call_id, "type": "function", "function": {
                        "name": call.name, "arguments": json.dumps(call.arguments),
                    }} for call in calls] or None,
                }}],
            })
        create.return_value = response()
        yield name, provider, create, response


def test_history_replay_preserves_ids_results_and_provider_payload(adapter):
    name, provider, create, response = adapter
    calls = (ToolCall("one", "read_file", {"path": "a.py"}), ToolCall("two", "read_file", {"path": "b.py"}))
    create.return_value = response(calls)
    history = [UserMessage("first task")]
    turn = provider.respond("system", history, [])
    assert turn.tool_calls == calls
    history.extend([turn, ToolResultsMessage((ToolResult("one", "a"), ToolResult("two", "denied", True))), UserMessage("followup")])
    before = deepcopy(history)
    provider.respond("updated system", history, [])
    wire = create.call_args.kwargs["messages"]
    assert wire[-1] == {"role": "user", "content": "followup"}
    assert history == before
    # The canonical transcript remains JSON serializable; SDK objects never escape.
    json.dumps([asdict(message) for message in history])
    if name == "minimax":
        assert wire[1]["content"][0]["signature"] == "fixture-signature"
        assert [item["tool_use_id"] for item in wire[2]["content"]] == ["one", "two"]
        assert wire[2]["content"][1]["is_error"] is True
        assert create.call_args.kwargs["system"] == "updated system"
    else:
        assert wire[0]["content"] == "updated system"
        assert wire[2]["reasoning_content"] == "opaque fixture"
        assert [item["tool_call_id"] for item in wire[3:5]] == ["one", "two"]


def test_same_provider_can_serve_independent_sessions_without_leaking_history(adapter):
    _, provider, create, _ = adapter
    provider.respond("system", [UserMessage("old session")], [])
    provider.respond("system", [UserMessage("new session")], [])
    wire = create.call_args.kwargs["messages"]
    assert "old session" not in json.dumps(wire)
    assert wire[-1]["content"] == "new session"


def test_generic_transcript_can_be_serialized_without_native_payload(adapter):
    _, provider, create, _ = adapter
    provider.respond("system", [
        UserMessage("task"), AssistantTurn("working", (ToolCall("one", "read_file", {"path": "a"}),)),
        ToolResultsMessage((ToolResult("one", "content"),)),
    ], [])
    assert "one" in json.dumps(create.call_args.kwargs["messages"])


def test_network_error_becomes_provider_error(adapter):
    name, provider, create, _ = adapter
    module = __import__("anthropic" if name == "minimax" else "openai")
    create.side_effect = module.APIConnectionError(request=httpx.Request("POST", "http://localhost"))
    with pytest.raises(ProviderError):
        provider.respond("system", [UserMessage("task")], [])


@pytest.mark.parametrize("arguments", ["{broken", "[]", "null", '"text"'])
def test_qwen_invalid_json_is_an_explicit_tool_error(arguments):
    with patch("myagent.providers.qwen.OpenAI") as client:
        provider = QwenProvider("fixture-key", "http://localhost", "fixture-model")
        client.return_value.chat.completions.create.return_value = ChatCompletion.model_validate({
            "id": "cmpl", "created": 0, "object": "chat.completion", "model": "test",
            "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
                "role": "assistant", "content": None, "tool_calls": [{"id": "broken", "type": "function", "function": {"name": "read_file", "arguments": arguments}}],
            }}],
        })
        turn = provider.respond("system", [UserMessage("task")], [])
        assert turn.tool_calls[0].parse_error
        assert turn.tool_calls[0].call_id == "broken"
        assert turn.provider_message["tool_calls"][0]["function"]["arguments"] == arguments
