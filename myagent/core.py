"""Provider- and tool-independent Agent orchestration loop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .protocol import AgentEvent, AgentResponse, EventType, ToolResult
from .session import Session, SessionStore
from .tools.base import ExecutionContext
from .tools.registry import ToolRegistry


SYSTEM_PROMPT = """You are a local coding agent. Use available tools to inspect and modify the workspace.
Respect tool errors, never invent tool results, and summarize completed changes and validation at the end.
"""


@dataclass
class Agent:
    provider: Any
    tools: ToolRegistry
    permission_engine: Any
    execution_context: ExecutionContext
    session_store: SessionStore | None = None
    system_prompt: str = SYSTEM_PROMPT
    event_handler: Callable[[AgentEvent], None] | None = None

    def run(self, task: str, max_steps: int | None = None) -> AgentResponse:
        if max_steps is None:
            max_steps = 20
        store = self.session_store or SessionStore()
        session = store.create(self.execution_context.workspace)
        session.messages.append({"role": "user", "content": task})
        self._emit(session, AgentEvent(EventType.TASK_STARTED, {"task": task, "session_id": session.session_id}))

        for _ in range(max_steps):
            turn = self.provider.respond(self.system_prompt, session.messages, self.tools.definitions())
            self._emit(session, AgentEvent(EventType.ASSISTANT_TURN, {"text": turn.text, "tool_calls": [call.name for call in turn.tool_calls]}))
            if not turn.tool_calls:
                self._emit(session, AgentEvent(EventType.TASK_COMPLETED, {"text": turn.text}))
                return AgentResponse(turn.text)

            results: list[ToolResult] = []
            for call in turn.tool_calls:
                if self.execution_context.cancellation_requested():
                    return AgentResponse("Task cancelled", False)
                tool = self.tools.get(call.name)
                if tool is None:
                    result = ToolResult(call.call_id, f"Unknown tool: {call.name}", True)
                elif not self.permission_engine.check(tool.spec.action, tool.resource(call.arguments)):
                    result = ToolResult(call.call_id, f"Permission denied: {call.name}", True)
                else:
                    self._emit(session, AgentEvent(EventType.TOOL_REQUESTED, {"name": call.name, "call_id": call.call_id}))
                    result = tool.execute(call.call_id, call.arguments, self.execution_context)
                results.append(result)
                self._emit(session, AgentEvent(EventType.TOOL_COMPLETED, {"call_id": result.call_id, "is_error": result.is_error, "content": result.content}))
            self.provider.append_tool_results(results)

        response = AgentResponse("Agent stopped after reaching the step limit.", False)
        self._emit(session, AgentEvent(EventType.ERROR, {"message": response.text}))
        return response

    def _emit(self, session: Session, event: AgentEvent) -> None:
        session.events.append(event)
        if self.event_handler:
            self.event_handler(event)
