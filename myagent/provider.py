"""Interfaces for model providers and tool-call protocol adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

from .protocol import AssistantTurn, Message


class ProviderError(RuntimeError):
    """A provider request failed in a recoverable, user-facing way."""


class LLMProvider(ABC):
    @abstractmethod
    def respond(
        self,
        system_prompt: str,
        messages: Iterable[Message],
        tool_definitions: list[dict[str, object]],
    ) -> AssistantTurn:
        """Translate the complete session history and return a turn without storing history."""
