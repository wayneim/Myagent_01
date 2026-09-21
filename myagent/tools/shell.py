"""Shell tool backed by an injectable sandbox implementation."""

from __future__ import annotations

from typing import Any

from .base import ExecutionContext, Tool, ToolSpec
from myagent.protocol import ToolResult


class ShellTool(Tool):
    spec = ToolSpec("bash", "Run a command in the workspace sandbox.", {"type": "object", "properties": {"command": {"type": "string"}, "timeout_seconds": {"type": "integer"}}, "required": ["command"]}, "shell")

    def execute(self, call_id: str, arguments: dict[str, Any], context: ExecutionContext) -> ToolResult:
        backend = getattr(context, "sandbox_backend", None)
        if backend is None:
            return ToolResult(call_id, "No sandbox backend configured", True)
        try:
            result = backend.run(arguments["command"], context.workspace, int(arguments.get("timeout_seconds", 30)))
            content = f"exit_code={result.exit_code}\nsandboxed={result.sandboxed}\n{result.stdout}\n{result.stderr}"
            return ToolResult(call_id, content[: context.max_output_chars], result.exit_code != 0)
        except Exception as exc:  # backend errors are returned to the model as tool failures
            return ToolResult(call_id, f"bash failed: {exc}", True)

    def resource(self, arguments: dict[str, Any]) -> str:
        return arguments.get("command", "")
