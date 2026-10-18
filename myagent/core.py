"""Provider- and tool-independent Agent loop; Session owns the complete transcript."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .provider import LLMProvider, ProviderError
from .protocol import AgentEvent, AgentResponse, EventType, ToolResult, ToolResultsMessage, UserMessage
from .security.permissions import PermissionEngine
from .session import Session, SessionStore
from .tools.base import ExecutionContext
from .tools.executor import ToolExecutor
from .tools.registry import ToolRegistry


SYSTEM_PROMPT = """You are a local coding agent. Use available tools to inspect and modify the workspace.
Read relevant files before editing. Respect tool errors and permission denials; never invent tool results.
Use failed validation or test output to correct your next action. Summarize changes and validation at the end.
"""


@dataclass
class Agent:
    provider: LLMProvider
    tools: ToolRegistry
    permission_engine: PermissionEngine
    execution_context: ExecutionContext
    session_store: SessionStore = field(default_factory=SessionStore)
    system_prompt: str = SYSTEM_PROMPT
    event_handler: Callable[[AgentEvent], None] | None = None

    def new_session(self) -> Session:
        return self.session_store.create(Path(self.execution_context.workspace))

    def run(self, task: str, max_steps: int = 20, *, session_id: str | None = None) -> AgentResponse:
        """Pass session_id to continue; omit it to start an isolated session."""
        if max_steps < 1:
            raise ValueError("max_steps must be at least 1")
        session = self.session_store.get(session_id) if session_id else self.new_session()
        if session.workspace != Path(self.execution_context.workspace).resolve():
            raise ValueError("Session belongs to a different workspace")
        session.messages.append(UserMessage(task))
        self._emit(session, AgentEvent(EventType.TASK_STARTED, {"task": task, "session_id": session.session_id}))
        executor = ToolExecutor(self.tools, self.permission_engine, self.execution_context)

        for _ in range(max_steps):
            if self.execution_context.cancellation_requested():
                return self._cancelled(session)
            try:
                turn = self.provider.respond(self.system_prompt, session.messages, self.tools.definitions())
            except ProviderError as exc:
                return self._failed(session, str(exc))
            except KeyboardInterrupt:
                return self._cancelled(session)
            session.messages.append(turn)
            self._emit(session, AgentEvent(EventType.ASSISTANT_TURN, {"text": turn.text, "tool_calls": [call.name for call in turn.tool_calls]}))
            if not turn.tool_calls:
                self._emit(session, AgentEvent(EventType.TASK_COMPLETED, {"text": turn.text}))
                return AgentResponse(turn.text, session_id=session.session_id)

            results: list[ToolResult] = []
            cancelled = False
            for call in turn.tool_calls:
                self._emit(session, AgentEvent(EventType.TOOL_REQUESTED, {"name": call.name, "call_id": call.call_id}))
                cancelled = cancelled or self.execution_context.cancellation_requested()
                try:
                    result = ToolResult(call.call_id, "Task cancelled; tool not executed", True) if cancelled else executor.execute(call)
                except KeyboardInterrupt:
                    cancelled = True
                    result = ToolResult(call.call_id, "Task interrupted; side effects may have occurred", True)
                results.append(result)
                self._emit(session, AgentEvent(EventType.TOOL_COMPLETED, {"call_id": result.call_id, "is_error": result.is_error, "content": result.content}))
            # Close every declared call even on cancellation, preserving replay order.
            session.messages.append(ToolResultsMessage(tuple(results)))
            if cancelled:
                return self._cancelled(session)

        return self._failed(session, "Agent stopped after reaching the step limit.")

    def _failed(self, session: Session, message: str) -> AgentResponse:
        self._emit(session, AgentEvent(EventType.ERROR, {"message": message}))
        return AgentResponse(message, False, session.session_id)

    def _cancelled(self, session: Session) -> AgentResponse:
        self._emit(session, AgentEvent(EventType.TASK_CANCELLED, {"message": "Task cancelled"}))
        return AgentResponse("Task cancelled", False, session.session_id)

    def _emit(self, session: Session, event: AgentEvent) -> None:
        session.events.append(event)
        if self.event_handler:
            self.event_handler(event)
