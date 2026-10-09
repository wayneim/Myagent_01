"""Qwen provider through the OpenAI-compatible Chat Completions API."""

from __future__ import annotations

import json
from typing import Iterable

from openai import APIError, APITimeoutError, OpenAI

from myagent.protocol import AssistantTurn, ToolCall, ToolResult
from myagent.provider import LLMProvider, ProviderError


class QwenProvider(LLMProvider):
    def __init__(self, api_key: str, base_url: str, model: str, max_tokens: int = 4096) -> None:
        if not api_key:
            raise ValueError("QWEN_API_KEY is required")
        self.model = model
        self.max_tokens = max_tokens
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self._messages: list[dict[str, object]] = []

    def respond(
        self,
        system_prompt: str,
        messages: Iterable[object],
        tool_definitions: list[dict[str, object]],
    ) -> AssistantTurn:
        if not self._messages:
            self._messages = [{"role": "system", "content": system_prompt}]
            self._messages.extend(
                dict(message) for message in messages if isinstance(message, dict)
            )
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=self._messages,
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": item["name"],
                            "description": item["description"],
                            "parameters": item["input_schema"],
                        },
                    }
                    for item in tool_definitions
                ] if tool_definitions else None,
            )
        except (APITimeoutError, APIError) as exc:
            raise ProviderError(f"Qwen request failed: {exc}") from exc

        choice = response.choices[0]
        message = choice.message
        self._messages.append({
            "role": "assistant",
            "content": message.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in (message.tool_calls or [])
            ] if message.tool_calls else None,
        })

        text_parts: list[str] = []
        calls: list[ToolCall] = []
        if message.content:
            text_parts.append(message.content)
        if message.tool_calls:
            for tc in message.tool_calls:
                try:
                    arguments = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    arguments = {}
                calls.append(ToolCall(tc.id, tc.function.name, arguments))
        return AssistantTurn("\n".join(text_parts), tuple(calls), response)

    def append_tool_results(self, results: Iterable[ToolResult]) -> None:
        for result in results:
            self._messages.append({
                "role": "tool",
                "tool_call_id": result.call_id,
                "content": result.content,
            })
