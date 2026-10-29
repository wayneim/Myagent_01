"""Read, search, write, and exact-edit tools."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterator

from jsonschema import Draft202012Validator, ValidationError

from .base import ExecutionContext, Tool, ToolSpec
from .file_changes import (
    EDIT_PARAMETERS, WRITE_PARAMETERS, FileChange, FileConflictError,
    commit_change, content_hash, prepare_content, resolve_edit_path, snapshot, validate_parent,
)
from myagent.protocol import ToolResult
from myagent.security.workspace import WorkspaceResolver


def _resolver(context: ExecutionContext) -> WorkspaceResolver:
    resolver = getattr(context, "workspace_resolver", None)
    if resolver is None:
        resolver = WorkspaceResolver(Path(context.workspace))
    return resolver


def _search_files(context: ExecutionContext, pattern: str) -> Iterator[Path]:
    resolver = _resolver(context)
    for path in resolver.iter_files(pattern):
        # Authorizing the query does not authorize every file it happens to match.
        if context.permission_engine.check("read", str(path.relative_to(resolver.root))):   # 校验操作资源的权限
            yield path

"""
文件读取工具
"""
class ReadFileTool(Tool):
    # 类属性赋值
    spec = ToolSpec("read_file", "Read UTF-8 text and return its full-file SHA-256 for expected_hash on edits, even when reading a line range.", {"type": "object", "properties": {"path": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}}, "required": ["path"]}, "read")

    def execute(self, call_id: str, arguments: dict[str, Any], context: ExecutionContext) -> ToolResult:
        try:
            path = _resolver(context).resolve(arguments["path"])
            data = path.read_bytes()
            digest = content_hash(data)
            lines = data.decode("utf-8").splitlines()
            start = max(1, int(arguments.get("start_line", 1)))
            end = min(len(lines), int(arguments.get("end_line", len(lines))))
            content = f"path={arguments['path']}\nsha256={digest}\n" + "\n".join(f"{i}: {lines[i - 1]}" for i in range(start, end + 1))
            return ToolResult(call_id, content[: context.max_output_chars], metadata={
                "sha256": digest, "path": arguments["path"],
                "start_line": start, "end_line": end,
                "truncated": len(content) > context.max_output_chars,
            })
        except (OSError, KeyError, ValueError) as exc:
            return ToolResult(call_id, f"read_file failed: {exc}", True)

    def resource(self, arguments: dict[str, Any]) -> str:
        return arguments.get("path", "")


"""
文件路径搜索工具，按通配符查找工作区中的文件
"""
class GlobTool(Tool):
    spec = ToolSpec("glob", "Find workspace files matching a glob pattern.", {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]}, "read")

    def execute(self, call_id: str, arguments: dict[str, Any], context: ExecutionContext) -> ToolResult:
        try:
            resolver = _resolver(context)
            paths: list[str] = []
            size = 0
            for path in _search_files(context, arguments.get("pattern", "**/*")):
                relative = str(path.relative_to(resolver.root))
                paths.append(relative)
                size += len(relative) + 1
                if len(paths) >= context.max_search_results or size >= context.max_output_chars:
                    return ToolResult(call_id, "\n".join(paths)[: context.max_output_chars], metadata={"truncated": True})
            return ToolResult(call_id, "\n".join(paths))
        except (OSError, ValueError, KeyError) as exc:
            return ToolResult(call_id, f"glob failed: {exc}", True)

    def resource(self, arguments: dict[str, Any]) -> str:
        return arguments.get("pattern", "*")


"""
文件内容搜索工具，按正则表达式查找工作区中的匹配行
"""
class GrepTool(Tool):
    spec = ToolSpec("grep", "Search workspace text files with a regular expression.", {"type": "object", "properties": {"pattern": {"type": "string"}, "glob": {"type": "string"}}, "required": ["pattern"]}, "read")

    def execute(self, call_id: str, arguments: dict[str, Any], context: ExecutionContext) -> ToolResult:
        try:
            expression = re.compile(arguments["pattern"])       # 用于匹配内容
            resolver = _resolver(context)
            matches: list[str] = []
            size = 0
            for index, path in enumerate(_search_files(context, arguments.get("glob", "**/*"))):       # 匹配文件
                if index >= context.max_search_files:
                    return ToolResult(call_id, "\n".join(matches), metadata={"truncated": True})
                try:
                    if path.stat().st_size > context.max_search_file_bytes:
                        continue
                    with path.open("rb") as stream:         # 二进制只读
                        if b"\x00" in stream.read(8_192):   # TODO 是否有空字节，是则可能为二进制文件，跳过（不准确）
                            continue
                    with path.open(encoding="utf-8") as stream:
                        for number, line in enumerate(stream, 1):
                            if expression.search(line):     # 正则搜索内容
                                match = f"{path.relative_to(resolver.root)}:{number}:{line.rstrip()[:1_000]}"
                                matches.append(match)
                                size += len(match) + 1
                                if len(matches) >= context.max_search_results or size >= context.max_output_chars:
                                    return ToolResult(call_id, "\n".join(matches)[: context.max_output_chars], metadata={"truncated": True})
                except (OSError, UnicodeDecodeError):
                    continue
            return ToolResult(call_id, "\n".join(matches))
        except (OSError, ValueError, KeyError, re.error) as exc:
            return ToolResult(call_id, f"grep failed: {exc}", True)

    def resource(self, arguments: dict[str, Any]) -> str:
        return arguments.get("glob", "*")


"""
文件编辑工具，精确替换文件中唯一匹配的文本
"""
class EditFileTool(Tool):
    spec = ToolSpec("edit_file", "Replace one unique exact text range. Pass expected_hash from read_file to reject stale edits.", EDIT_PARAMETERS, "edit")

    def execute(self, call_id: str, arguments: dict[str, Any], context: ExecutionContext) -> ToolResult:
        return _execute_change(call_id, "edit", arguments, context, self.spec.parameters)

    def resource(self, arguments: dict[str, Any]) -> str:
        return arguments.get("path", "")


"""
文件写入工具，创建文件或覆盖已有文件内容
"""
class WriteFileTool(Tool):
    spec = ToolSpec("write_file", "Create or replace UTF-8 text. Use expected_hash from read_file for replacement, or 'missing' for create-only.", WRITE_PARAMETERS, "edit")

    def execute(self, call_id: str, arguments: dict[str, Any], context: ExecutionContext) -> ToolResult:
        return _execute_change(call_id, "write", arguments, context, self.spec.parameters)

    def resource(self, arguments: dict[str, Any]) -> str:
        return arguments.get("path", "")


def _execute_change(call_id: str, kind: str, arguments: dict[str, Any], context: ExecutionContext, schema: dict) -> ToolResult:
    try:
        Draft202012Validator(schema).validate(arguments)
        path = resolve_edit_path(context, arguments["path"])
        validate_parent(path)
        original = snapshot(path)
        content = prepare_content(kind, arguments, original)
        change = FileChange(path, original, content)
        # Detect a changed link/path before writing, in addition to content checks.
        if resolve_edit_path(context, arguments["path"], authorize_alias=False) != path:
            raise FileConflictError("File target changed after preparation")
        changed = commit_change(change)
        digest = content_hash(content)
        verb = ("Updated" if kind == "edit" else "Wrote") if changed else "Unchanged"
        return ToolResult(call_id, f"{verb} {arguments['path']}\nsha256={digest}", metadata={
            "sha256": digest, "modified_files": [arguments["path"]] if changed else [],
        })
    except (OSError, KeyError, ValueError, ValidationError) as exc:
        error_kind = "conflict" if isinstance(exc, FileConflictError) else "file_error"
        reason = exc.message if isinstance(exc, ValidationError) else str(exc)
        return ToolResult(call_id, f"{kind}_file failed: {reason}", True, {"kind": error_kind, "modified_files": []})
