"""MiniMax provider through the Anthropic-compatible Messages API."""

from __future__ import annotations

from copy import deepcopy
from typing import Iterable

from anthropic import APIError, APITimeoutError, Anthropic

from myagent.protocol import AssistantTurn, Message, ToolCall, ToolResultsMessage, UserMessage
from myagent.provider import LLMProvider, ProviderError


class MiniMaxProvider(LLMProvider):
    def __init__(self, api_key: str, base_url: str, model: str, max_tokens: int = 4096) -> None:
        if not api_key:
            raise ValueError("MINIMAX_API_KEY is required")
        self.model = model
        self.max_tokens = max_tokens
        self.client = Anthropic(api_key=api_key, base_url=base_url)

    def respond(
        self,
        system_prompt: str,
        messages: Iterable[Message],
        tool_definitions: list[dict[str, object]],
    ) -> AssistantTurn:
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system_prompt,
                messages=self._serialize(messages),
                tools=[{"name": item["name"], "description": item["description"], "input_schema": item["input_schema"]} for item in tool_definitions],
            )
        except (APITimeoutError, APIError) as exc:
            raise ProviderError(f"MiniMax request failed: {exc}") from exc

        text_parts: list[str] = []
        calls: list[ToolCall] = []
        for block in response.content:
            if getattr(block, "type", None) == "text":
                text_parts.append(getattr(block, "text", ""))
            elif getattr(block, "type", None) == "tool_use":
                arguments = block.input
                error = None if isinstance(arguments, dict) else "Tool arguments must be a JSON object"
                calls.append(ToolCall(block.id, block.name, arguments if error is None else {}, parse_error=error))
        payload = {"role": "assistant", "content": [block.model_dump(mode="json", exclude_none=True) for block in response.content]}
        return AssistantTurn("\n".join(text_parts), tuple(calls), payload, "minimax")

    def _serialize(self, messages: Iterable[Message]) -> list[dict[str, object]]:
        history: list[dict[str, object]] = []
        for message in messages:
            if isinstance(message, UserMessage):
                history.append({"role": "user", "content": message.content})
            elif isinstance(message, AssistantTurn):
                if message.provider == "minimax" and message.provider_message is not None:
                    history.append(deepcopy(message.provider_message))
                else:
                    content = [{"type": "text", "text": message.text}] if message.text else []
                    content.extend({"type": "tool_use", "id": call.call_id, "name": call.name, "input": call.arguments} for call in message.tool_calls)
                    history.append({"role": "assistant", "content": content})
            elif isinstance(message, ToolResultsMessage):
                history.append({"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": result.call_id, "content": result.content, "is_error": result.is_error}
                    for result in message.results
                ]})
            else:
                raise ProviderError(f"Unsupported session message: {type(message).__name__}")
        return history
