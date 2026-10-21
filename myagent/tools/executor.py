"""One execution path: validate -> authorize -> execute -> normalize the result."""

from __future__ import annotations

from dataclasses import dataclass, replace

from jsonschema import Draft202012Validator, ValidationError

from myagent.protocol import ToolCall, ToolResult
from myagent.security.permissions import PermissionEngine
from .base import ExecutionContext
from .registry import ToolRegistry


@dataclass
class ToolExecutor:
    tools: ToolRegistry
    permissions: PermissionEngine
    context: ExecutionContext

    def execute(self, call: ToolCall) -> ToolResult:
        try:
            if call.parse_error:
                return self._error(call, "invalid_arguments", call.parse_error)
            tool = self.tools.get(call.name)
            if tool is None:
                return self._error(call, "unknown_tool", f"Unknown tool: {call.name}")
            Draft202012Validator(tool.spec.parameters).validate(call.arguments)     # 校验参数是否正确（是否有必填参数等）
            if not all(self.permissions.check(tool.spec.action, resource) for resource in tool.resources(call.arguments)):
                return self._error(call, "permission_denied", f"Permission denied: {call.name}")
            result = tool.execute(call.call_id, call.arguments, self.context)
            if not isinstance(result, ToolResult) or result.call_id != call.call_id:
                raise ValueError("Tool returned an invalid result or mismatched call_id")
            limit = self.context.max_output_chars
            if len(result.content) > limit:
                result = replace(result, content=result.content[:limit], metadata={**result.metadata, "truncated": True})
            return result
        except ValidationError as exc:
            return self._error(call, "invalid_arguments", f"Invalid arguments for {call.name}: {exc.message}")
        except Exception as exc:
            # KeyboardInterrupt deliberately propagates so Core can close the tool batch.
            return self._error(call, "execution_error", f"{call.name} failed: {type(exc).__name__}: {exc}")

    def _error(self, call: ToolCall, kind: str, message: str) -> ToolResult:
        return ToolResult(call.call_id, message[: self.context.max_output_chars], True, {"kind": kind})
