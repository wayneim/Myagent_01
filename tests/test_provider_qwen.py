"""Contract tests for Qwen Provider using mocked OpenAI responses."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from myagent.providers.qwen import QwenProvider
from myagent.protocol import ToolResult


def test_qwen_provider_converts_tool_definitions() -> None:
    with patch("myagent.providers.qwen.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "test"
        mock_response.choices[0].message.tool_calls = None
        mock_client.chat.completions.create.return_value = mock_response

        provider = QwenProvider("test-key", "http://localhost", "qwen-plus")
        provider.respond(
            "system prompt",
            [{"role": "user", "content": "hello"}],
            [
                {
                    "name": "read_file",
                    "description": "Read a file",
                    "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}},
                }
            ],
        )

        call_args = mock_client.chat.completions.create.call_args
        assert call_args.kwargs["tools"][0]["type"] == "function"
        assert call_args.kwargs["tools"][0]["function"]["name"] == "read_file"
        assert call_args.kwargs["tools"][0]["function"]["parameters"]["type"] == "object"


def test_qwen_provider_parses_tool_calls() -> None:
    with patch("myagent.providers.qwen.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_123"
        mock_tool_call.function.name = "read_file"
        mock_tool_call.function.arguments = '{"path": "test.txt"}'
        mock_response.choices[0].message.tool_calls = [mock_tool_call]
        mock_client.chat.completions.create.return_value = mock_response

        provider = QwenProvider("test-key", "http://localhost", "qwen-plus")
        turn = provider.respond("system", [{"role": "user", "content": "read"}], [])

        assert len(turn.tool_calls) == 1
        assert turn.tool_calls[0].call_id == "call_123"
        assert turn.tool_calls[0].name == "read_file"
        assert turn.tool_calls[0].arguments == {"path": "test.txt"}


def test_qwen_provider_appends_tool_results() -> None:
    with patch("myagent.providers.qwen.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "done"
        mock_response.choices[0].message.tool_calls = None
        mock_client.chat.completions.create.return_value = mock_response

        provider = QwenProvider("test-key", "http://localhost", "qwen-plus")
        provider.respond("system", [{"role": "user", "content": "test"}], [])
        provider.append_tool_results([ToolResult("call_123", "file content")])

        assert provider._messages[-1]["role"] == "tool"
        assert provider._messages[-1]["tool_call_id"] == "call_123"
        assert provider._messages[-1]["content"] == "file content"


def test_qwen_provider_includes_system_message() -> None:
    with patch("myagent.providers.qwen.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "response"
        mock_response.choices[0].message.tool_calls = None
        mock_client.chat.completions.create.return_value = mock_response

        provider = QwenProvider("test-key", "http://localhost", "qwen-plus")
        provider.respond("system prompt", [{"role": "user", "content": "hello"}], [])

        assert provider._messages[0]["role"] == "system"
        assert provider._messages[0]["content"] == "system prompt"
