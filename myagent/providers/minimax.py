"""MiniMax provider through the Anthropic-compatible Messages API."""

from __future__ import annotations

from typing import Iterable

from anthropic import APIError, APITimeoutError, Anthropic

from myagent.protocol import AssistantTurn, ToolCall, ToolResult
from myagent.provider import LLMProvider, ProviderError


class MiniMaxProvider(LLMProvider):
    def __init__(self, api_key: str, base_url: str, model: str, max_tokens: int = 4096) -> None:
        if not api_key:
            raise ValueError("MINIMAX_API_KEY is required")
        self.model = model
        self.max_tokens = max_tokens
        self.client = Anthropic(api_key=api_key, base_url=base_url)
        self._messages: list[dict[str, object]] = []

    def respond(
        self,
        system_prompt: str,
        messages: Iterable[object],
        tool_definitions: list[dict[str, object]],
    ) -> AssistantTurn:
        if not self._messages:
            self._messages = [dict(message) for message in messages if isinstance(message, dict)]
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system_prompt,
                messages=self._messages,
                tools=[{"name": item["name"], "description": item["description"], "input_schema": item["input_schema"]} for item in tool_definitions],
            )
        except (APITimeoutError, APIError) as exc:
            raise ProviderError(f"MiniMax request failed: {exc}") from exc

        self._messages.append({"role": "assistant", "content": response.content})
        text_parts: list[str] = []
        calls: list[ToolCall] = []
        for block in response.content:
            if getattr(block, "type", None) == "text":
                text_parts.append(getattr(block, "text", ""))
            elif getattr(block, "type", None) == "tool_use":
                calls.append(ToolCall(getattr(block, "id"), getattr(block, "name"), dict(getattr(block, "input", {}))))
        return AssistantTurn("\n".join(text_parts), tuple(calls), response)

    def append_tool_results(self, results: Iterable[ToolResult]) -> None:
        content = [
            {"type": "tool_result", "tool_use_id": result.call_id, "content": result.content, "is_error": result.is_error}
            for result in results
        ]
        self._messages.append({"role": "user", "content": content})
