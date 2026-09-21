"""Workspace path resolution and sensitive-file protection."""

from __future__ import annotations

from pathlib import Path


class WorkspaceViolation(ValueError):
    """A path is outside the workspace or is otherwise protected."""


class WorkspaceResolver:
    def __init__(self, root: Path, sensitive_names: tuple[str, ...] = (".env", ".env.*")) -> None:
        self.root = root.resolve()
        self.sensitive_names = sensitive_names

    def resolve(self, value: str, *, allow_sensitive: bool = False) -> Path:
        candidate = (self.root / value).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise WorkspaceViolation(f"Path outside workspace: {value}") from exc
        if not allow_sensitive and self._is_sensitive(candidate):
            raise WorkspaceViolation(f"Sensitive path is protected: {value}")
        return candidate

    def _is_sensitive(self, path: Path) -> bool:
        return any(path.match(pattern) or any(part == pattern for part in path.parts) for pattern in self.sensitive_names)
