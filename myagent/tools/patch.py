"""Small structured patch tool for multi-file changes."""

from __future__ import annotations

from typing import Any

from .base import ExecutionContext, Tool, ToolSpec
from .files import EditFileTool, WriteFileTool
from myagent.protocol import ToolResult


class ApplyPatchTool(Tool):
    spec = ToolSpec("apply_patch", "Apply a list of exact file operations.", {"type": "object", "properties": {"operations": {"type": "array", "items": {"type": "object"}}}, "required": ["operations"]}, "edit")

    def execute(self, call_id: str, arguments: dict[str, Any], context: ExecutionContext) -> ToolResult:
        operations = arguments.get("operations", [])
        if not isinstance(operations, list) or not operations:
            return ToolResult(call_id, "apply_patch requires a non-empty operations list", True)
        results: list[str] = []
        for index, operation in enumerate(operations):
            kind = operation.get("kind")
            if kind == "edit":
                result = EditFileTool().execute(f"{call_id}-{index}", operation, context)
            elif kind == "write":
                result = WriteFileTool().execute(f"{call_id}-{index}", operation, context)
            else:
                return ToolResult(call_id, f"Unsupported patch operation: {kind}", True)
            if result.is_error:
                return ToolResult(call_id, f"Patch stopped at operation {index}: {result.content}", True)
            results.append(result.content)
        return ToolResult(call_id, "\n".join(results))

    def resource(self, arguments: dict[str, Any]) -> str:
        return ",".join(str(item.get("path", "")) for item in arguments.get("operations", []))
