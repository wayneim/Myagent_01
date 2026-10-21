"""Provider-independent messages, tool calls, and agent events."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

"""
事件类型
"""
class EventType(str, Enum):
    TASK_STARTED = "task_started"
    ASSISTANT_TURN = "assistant_turn"
    TOOL_REQUESTED = "tool_requested"
    PERMISSION_REQUESTED = "permission_requested"
    TOOL_COMPLETED = "tool_completed"
    TASK_COMPLETED = "task_completed"
    TASK_CANCELLED = "task_cancelled"
    ERROR = "error"

"""
工具调用请求，包含调用标识、工具名称和参数
"""
@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any]
    protocol: str = "native"        # 工具调用来自哪种协议（api原生？普通文本解析？），当前为预留标识
    parse_error: str | None = None  # 记录参数解析错误


"""
单个工具调用的执行结果，通过调用标识与请求对应
"""
@dataclass(frozen=True)
class ToolResult:
    call_id: str
    content: str
    is_error: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


"""
模型一轮回复，包含文本、工具调用和用于历史回放的原始消息
"""
@dataclass(frozen=True)
class AssistantTurn:
    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    # JSON-compatible payload, never an SDK object. Preserve opaque blocks for replay.
    provider_message: dict[str, Any] | None = None
    provider: str | None = None


"""
用户消息，保存用户输入的任务或追问内容
"""
@dataclass(frozen=True)
class UserMessage:
    content: str


"""
一轮工具调用的结果消息，汇总本轮各个工具的执行结果
"""
@dataclass(frozen=True)
class ToolResultsMessage:
    results: tuple[ToolResult, ...]


Message = UserMessage | AssistantTurn | ToolResultsMessage


"""
Agent 运行事件，记录事件类型及数据，供会话保存和外部处理
"""
@dataclass(frozen=True)
class AgentEvent:
    type: EventType
    data: dict[str, Any] = field(default_factory=dict)


"""
一次任务运行的返回结果，包含回复文本、完成状态和会话标识
"""
@dataclass(frozen=True)
class AgentResponse:
    text: str
    completed: bool = True
    session_id: str | None = None
