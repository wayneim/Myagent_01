"""Shared preparation and optimistic conflict checks for file edits.

No writes happen during preparation. Each commit uses a same-directory unique
temporary, but multiple commits are not a filesystem transaction or a file lock.
"""

from __future__ import annotations

import hashlib
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .base import ExecutionContext
from myagent.security.workspace import WorkspaceResolver


EXPECTED_HASH_SCHEMA = {
    "type": "string",
    "pattern": "^(?:[0-9a-fA-F]{64}|missing)$",
    "description": "Expected full-file SHA-256 from read_file; 'missing' requires a new file. Omit for no prior-read version check.",
}
EDIT_PARAMETERS = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "minLength": 1},
        "old_string": {"type": "string", "minLength": 1},
        "new_string": {"type": "string"},
        "expected_hash": EXPECTED_HASH_SCHEMA,
    },
    "required": ["path", "old_string", "new_string"],
    "additionalProperties": False,
}
WRITE_PARAMETERS = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "minLength": 1},
        "content": {"type": "string"},
        "expected_hash": EXPECTED_HASH_SCHEMA,
    },
    "required": ["path", "content"],
    "additionalProperties": False,
}


class FileConflictError(ValueError):
    """The file differs from the expected or prepared version."""


@dataclass
class FileChange:
    path: Path
    original: bytes | None
    content: bytes


def content_hash(content: bytes | None) -> str:
    return "missing" if content is None else hashlib.sha256(content).hexdigest()    # TODO 文件太大是否会有问题？


def snapshot(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def resolve_edit_path(context: ExecutionContext, value: str, *, authorize_alias: bool = True) -> Path:
    resolver = context.workspace_resolver or WorkspaceResolver(Path(context.workspace))
    path = resolver.resolve(value)
    # ToolExecutor authorizes the declared path. A resolved alias must not bypass
    # a deny rule on the actual target (including links inside the workspace).
    if authorize_alias and path != resolver.root / value:
        resource = str(path.relative_to(resolver.root))
        if not context.permission_engine.check("edit", resource):
            raise ValueError(f"Permission denied: {resource}")
    return path


def validate_parent(path: Path) -> None:
    for parent in path.parents:
        if parent.exists() and not parent.is_dir():
            raise ValueError(f"File parent is not a directory: {parent}")


def prepare_content(kind: str, arguments: dict[str, Any], current: bytes | None) -> bytes:
    expected = arguments.get("expected_hash")
    if expected is not None and expected.lower() != content_hash(current):
        raise FileConflictError(f"Content conflict for {arguments['path']}: expected_hash does not match; read the file again")
    if kind == "write":
        return arguments["content"].encode("utf-8")
    if current is None:
        raise ValueError(f"Cannot edit a missing file: {arguments['path']}")
    original = current.decode("utf-8")
    old = arguments["old_string"]
    count = original.count(old)
    if count != 1:
        raise ValueError(f"edit_file requires exactly one match, found {count}")
    return original.replace(old, arguments["new_string"], 1).encode("utf-8")


def check_unchanged(change: FileChange) -> None:
    if snapshot(change.path) != change.original:
        raise FileConflictError(f"Content conflict for {change.path.name}: file changed after preparation")


def commit_change(change: FileChange) -> bool:
    """Recheck immediately before replacement; external writers are not locked."""
    check_unchanged(change)
    if change.content == change.original:
        return False
    change.path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=change.path.parent,
            prefix=f".{change.path.name}.", suffix=".myagent.tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(change.content)
        # Closing first is required for replacement on Windows. Recheck after
        # temporary output as another editor may have changed the target meanwhile.
        check_unchanged(change)
        temporary.replace(change.path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return True
