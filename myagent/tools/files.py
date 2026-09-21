"""Read, search, write, and exact-edit tools."""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Any

from .base import ExecutionContext, Tool, ToolSpec
from myagent.protocol import ToolResult
from myagent.security.workspace import WorkspaceResolver


def _resolver(context: ExecutionContext) -> WorkspaceResolver:
    resolver = getattr(context, "workspace_resolver", None)
    if resolver is None:
        resolver = WorkspaceResolver(Path(context.workspace))
    return resolver


class ReadFileTool(Tool):
    spec = ToolSpec("read_file", "Read a text file in the workspace.", {"type": "object", "properties": {"path": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}}, "required": ["path"]}, "read", True, True)

    def execute(self, call_id: str, arguments: dict[str, Any], context: ExecutionContext) -> ToolResult:
        try:
            path = _resolver(context).resolve(arguments["path"])
            lines = path.read_text(encoding="utf-8").splitlines()
            start = max(1, int(arguments.get("start_line", 1)))
            end = min(len(lines), int(arguments.get("end_line", len(lines))))
            content = "\n".join(f"{i}: {lines[i - 1]}" for i in range(start, end + 1))
            return ToolResult(call_id, content[: context.max_output_chars])
        except (OSError, KeyError, ValueError) as exc:
            return ToolResult(call_id, f"read_file failed: {exc}", True)

    def resource(self, arguments: dict[str, Any]) -> str:
        return arguments.get("path", "")


class GlobTool(Tool):
    spec = ToolSpec("glob", "Find workspace files matching a glob pattern.", {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]}, "read", True, True)

    def execute(self, call_id: str, arguments: dict[str, Any], context: ExecutionContext) -> ToolResult:
        pattern = arguments.get("pattern", "**/*")
        root = Path(context.workspace)
        paths = [str(path.relative_to(root)) for path in root.glob(pattern) if path.is_file()]
        return ToolResult(call_id, "\n".join(paths)[: context.max_output_chars])

    def resource(self, arguments: dict[str, Any]) -> str:
        return arguments.get("pattern", "*")


class GrepTool(Tool):
    spec = ToolSpec("grep", "Search workspace text files with a regular expression.", {"type": "object", "properties": {"pattern": {"type": "string"}, "glob": {"type": "string"}}, "required": ["pattern"]}, "read", True, True)

    def execute(self, call_id: str, arguments: dict[str, Any], context: ExecutionContext) -> ToolResult:
        expression = re.compile(arguments["pattern"])
        root = Path(context.workspace)
        file_pattern = arguments.get("glob", "**/*")
        matches: list[str] = []
        for path in root.glob(file_pattern):
            if not path.is_file():
                continue
            try:
                for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                    if expression.search(line):
                        matches.append(f"{path.relative_to(root)}:{number}:{line}")
            except (OSError, UnicodeDecodeError):
                continue
        return ToolResult(call_id, "\n".join(matches)[: context.max_output_chars])

    def resource(self, arguments: dict[str, Any]) -> str:
        return arguments.get("glob", "*")


class EditFileTool(Tool):
    spec = ToolSpec("edit_file", "Replace one unique text range in a workspace file.", {"type": "object", "properties": {"path": {"type": "string"}, "old_string": {"type": "string"}, "new_string": {"type": "string"}}, "required": ["path", "old_string", "new_string"]}, "edit")

    def execute(self, call_id: str, arguments: dict[str, Any], context: ExecutionContext) -> ToolResult:
        try:
            path = _resolver(context).resolve(arguments["path"])
            original = path.read_text(encoding="utf-8")
            old = arguments["old_string"]
            count = original.count(old)
            if count != 1:
                return ToolResult(call_id, f"edit_file requires exactly one match, found {count}", True)
            updated = original.replace(old, arguments["new_string"], 1)
            _atomic_write(path, updated)
            return ToolResult(call_id, f"Updated {arguments['path']}")
        except (OSError, KeyError, UnicodeDecodeError, ValueError) as exc:
            return ToolResult(call_id, f"edit_file failed: {exc}", True)

    def resource(self, arguments: dict[str, Any]) -> str:
        return arguments.get("path", "")


class WriteFileTool(Tool):
    spec = ToolSpec("write_file", "Create or replace a workspace text file.", {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}, "edit")

    def execute(self, call_id: str, arguments: dict[str, Any], context: ExecutionContext) -> ToolResult:
        try:
            path = _resolver(context).resolve(arguments["path"])
            path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(path, arguments["content"])
            return ToolResult(call_id, f"Wrote {arguments['path']}")
        except (OSError, KeyError, ValueError) as exc:
            return ToolResult(call_id, f"write_file failed: {exc}", True)

    def resource(self, arguments: dict[str, Any]) -> str:
        return arguments.get("path", "")


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.myagent.tmp")
    temporary.write_text(content, encoding="utf-8", newline="")
    temporary.replace(path)
