"""Small structured patch tool for multi-file changes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

from .base import ExecutionContext, Tool, ToolSpec
from .file_changes import (
    EDIT_PARAMETERS, WRITE_PARAMETERS, FileChange, FileConflictError,
    check_unchanged, commit_change, content_hash, prepare_content,
    resolve_edit_path, snapshot, validate_parent,
)
from myagent.protocol import ToolResult


"""
补丁工具，先在内存顺序模拟全部操作，再按文件提交；预检失败零写入，提交失败不回滚
"""
class ApplyPatchTool(Tool):
    # kind/path/content or old_string/new_string are described and validated before reads.
    spec = ToolSpec("apply_patch", "Preflight all operations in memory, then commit each final file once. Same-file operations see earlier staged results; expected_hash refers to that staged version. Commit failure may leave reported earlier files changed; no rollback.", {
        "type": "object",
        "properties": {"operations": {
            "type": "array", "minItems": 1,
            "items": {"oneOf": [
                {**EDIT_PARAMETERS, "properties": {**EDIT_PARAMETERS["properties"], "kind": {"const": "edit"}}, "required": ["kind", *EDIT_PARAMETERS["required"]]},
                {**WRITE_PARAMETERS, "properties": {**WRITE_PARAMETERS["properties"], "kind": {"const": "write"}}, "required": ["kind", *WRITE_PARAMETERS["required"]]},
            ]},
        }},
        "required": ["operations"], "additionalProperties": False,
    }, "edit")

    def execute(self, call_id: str, arguments: dict[str, Any], context: ExecutionContext) -> ToolResult:
        phase = "preflight"
        modified: list[str] = []
        current_file: str | None = None
        changes: dict[Path, FileChange] = {}
        aliases: dict[str, Path] = {}
        root = context.workspace_resolver.root if context.workspace_resolver else Path(context.workspace).resolve()
        try:
            Draft202012Validator(self.spec.parameters).validate(arguments)
            operations = arguments["operations"]
            for operation in operations:
                current_file = operation["path"]
                path = resolve_edit_path(context, current_file)
                if current_file in aliases and aliases[current_file] != path:
                    raise FileConflictError(f"File target changed during preflight: {current_file}")
                validate_parent(path)
                aliases[current_file] = path
                previous = changes.get(path)
                original = snapshot(path) if previous is None else previous.content
                content = prepare_content(operation["kind"], operation, original)
                changes[path] = FileChange(path, original if previous is None else previous.original, content)
            # A planned file cannot also be a parent directory of another target.
            for path in changes:
                if any(parent in changes for parent in path.parents):
                    current_file = str(path.relative_to(root))
                    raise ValueError(f"Patch targets conflict as file and directory: {path.relative_to(root)}")
            for path, change in changes.items():
                current_file = str(path.relative_to(root))
                self._check_targets(context, {name: target for name, target in aliases.items() if target == path})
                check_unchanged(change)
            phase = "commit"
            hashes = {}
            for path, change in changes.items():
                current_file = str(path.relative_to(root))
                self._check_targets(context, {name: target for name, target in aliases.items() if target == path})
                if commit_change(change):
                    modified.append(current_file)
                hashes[current_file] = content_hash(change.content)
            content = f"Applied {len(operations)} operations; modified {len(modified)} files.\n" + "\n".join(
                f"{name}: sha256={digest}" for name, digest in hashes.items()
            )
            return ToolResult(call_id, content, metadata={"modified_files": modified, "hashes": hashes})
        except (OSError, KeyError, ValueError, ValidationError) as exc:
            kind = "conflict" if isinstance(exc, FileConflictError) else "patch_error"
            reason = exc.message if isinstance(exc, ValidationError) else str(exc)
            message = f"Patch {phase} failed.\nModified files: {modified}.\nFailed file: {current_file or 'schema validation'}.\nNo rollback performed.\nReason: {reason}"
            return ToolResult(call_id, message, True, {
                "kind": kind, "phase": phase, "modified_files": modified, "failed_file": current_file,
            })

    @staticmethod
    def _check_targets(context: ExecutionContext, aliases: dict[str, Path]) -> None:
        for name, path in aliases.items():
            if resolve_edit_path(context, name, authorize_alias=False) != path:
                raise FileConflictError(f"File target changed after preparation: {name}")

    def resource(self, arguments: dict[str, Any]) -> str:
        return ",".join(str(item.get("path", "")) for item in arguments.get("operations", []))

    def resources(self, arguments: dict[str, Any]) -> list[str]:
        return [str(item.get("path", "")) for item in arguments.get("operations", [])]
