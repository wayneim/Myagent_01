"""Provider-independent messages, tool calls, and agent events."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventType(str, Enum):
    TASK_STARTED = "task_started"
    ASSISTANT_TURN = "assistant_turn"
    TOOL_REQUESTED = "tool_requested"
    PERMISSION_REQUESTED = "permission_requested"
    TOOL_COMPLETED = "tool_completed"
    TASK_COMPLETED = "task_completed"
    ERROR = "error"


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any]
    protocol: str = "native"


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    content: str
    is_error: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AssistantTurn:
    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    provider_message: Any = None


@dataclass(frozen=True)
class AgentEvent:
    type: EventType
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentResponse:
    text: str
    completed: bool = True
