"""Interfaces for model providers and tool-call protocol adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

from .protocol import AssistantTurn, ToolResult


class ProviderError(RuntimeError):
    """A provider request failed in a recoverable, user-facing way."""


class LLMProvider(ABC):
    @abstractmethod
    def respond(
        self,
        system_prompt: str,
        messages: Iterable[object],
        tool_definitions: list[dict[str, object]],
    ) -> AssistantTurn:
        """Return the next normalized assistant turn."""

    @abstractmethod
    def append_tool_results(self, results: Iterable[ToolResult]) -> None:
        """Record results in the provider-specific conversation state."""
