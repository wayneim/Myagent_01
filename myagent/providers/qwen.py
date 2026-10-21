"""Qwen provider through the OpenAI-compatible Chat Completions API."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Iterable

from openai import APIError, APITimeoutError, OpenAI

from myagent.protocol import AssistantTurn, Message, ToolCall, ToolResultsMessage, UserMessage
from myagent.provider import LLMProvider, ProviderError


class QwenProvider(LLMProvider):
    def __init__(self, api_key: str, base_url: str, model: str, max_tokens: int = 4096) -> None:
        if not api_key:
            raise ValueError("QWEN_API_KEY is required")
        self.model = model
        self.max_tokens = max_tokens
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def respond(
        self,
        system_prompt: str,
        messages: Iterable[Message],
        tool_definitions: list[dict[str, object]],
    ) -> AssistantTurn:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[{"role": "system", "content": system_prompt}, *self._serialize(messages)],
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

        if not response.choices:
            raise ProviderError("Qwen returned no response choices")
        choice = response.choices[0]
        message = choice.message

        text_parts: list[str] = []
        calls: list[ToolCall] = []
        if message.content:
            text_parts.append(message.content)
        if message.tool_calls:
            for tc in message.tool_calls:
                error = None
                try:
                    arguments = json.loads(tc.function.arguments)
                    if not isinstance(arguments, dict):
                        error = "Tool arguments must be a JSON object"
                        arguments = {}
                except (json.JSONDecodeError, TypeError) as exc:
                    arguments = {}
                    error = f"Invalid tool JSON: {exc}"
                calls.append(ToolCall(tc.id, tc.function.name, arguments, parse_error=error))
        payload = message.model_dump(mode="json", exclude_none=True)    # 将原始信息转为json格式存入provider message
        return AssistantTurn("\n".join(text_parts), tuple(calls), payload, "qwen")

    def _serialize(self, messages: Iterable[Message]) -> list[dict[str, object]]:
        history: list[dict[str, object]] = []
        for message in messages:
            if isinstance(message, UserMessage):
                history.append({"role": "user", "content": message.content})
            elif isinstance(message, AssistantTurn):
                if message.provider == "qwen" and message.provider_message is not None:
                    history.append(deepcopy(message.provider_message))      # 优先使用llm返回的信息，原样传回
                else:
                    payload = {"role": "assistant", "content": message.text or None}
                    if message.tool_calls:
                        payload["tool_calls"] = [
                            {"id": call.call_id, "type": "function", "function": {"name": call.name, "arguments": json.dumps(call.arguments)}}
                            for call in message.tool_calls
                        ]
                    history.append(payload)
            elif isinstance(message, ToolResultsMessage):
                history.extend({"role": "tool", "tool_call_id": result.call_id, "content": result.content} for result in message.results)
            else:
                raise ProviderError(f"Unsupported session message: {type(message).__name__}")
        return history
