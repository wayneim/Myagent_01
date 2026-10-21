"""Workspace path resolution and sensitive-file protection."""

from __future__ import annotations

from pathlib import Path
from fnmatch import fnmatchcase
from typing import Iterator


class WorkspaceViolation(ValueError):
    """A path is outside the workspace or is otherwise protected."""


class WorkspaceResolver:
    def __init__(self, root: Path, sensitive_names: tuple[str, ...] = (".env", ".env.*")) -> None:
        self.root = root.resolve()  # 转为绝对路径
        self.sensitive_names = sensitive_names

    """
    判断是否在工作目录内
    """
    def resolve(self, value: str, *, allow_sensitive: bool = False) -> Path:
        requested = self.root / value
        candidate = requested.resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise WorkspaceViolation(f"Path outside workspace: {value}") from exc
        if not allow_sensitive and (self._is_sensitive(requested) or self._is_sensitive(candidate)):
            raise WorkspaceViolation(f"Sensitive path is protected: {value}")
        return candidate

    def _is_sensitive(self, path: Path) -> bool:
        return any(fnmatchcase(part.casefold(), pattern.casefold()) for part in path.parts for pattern in self.sensitive_names)

    def iter_files(self, pattern: str) -> Iterator[Path]:
        """Search results obey the same path rules as direct reads, including symlinks."""
        query = Path(pattern)
        # 是否为绝对路径；是否包含盘符；是否含有返回上级目录的路径段（保守控制，防止遍历工作目录外的文件）
        if query.is_absolute() or query.drive or ".." in query.parts:
            raise WorkspaceViolation("Search pattern must stay inside the workspace")
        ignored = {".git", ".venv", "venv", "__pycache__", ".myagent", ".pytest_cache"}
        for path in self.root.glob(pattern):            # 获取符合通配符的路径
            relative = path.relative_to(self.root)      # 将匹配路径转换成相对于工作区根目录的路径
            if any(part in ignored or part.endswith(".egg-info") for part in relative.parts):
                continue
            try:
                resolved = self.resolve(str(relative))
                if resolved.is_file():
                    yield path
            except (WorkspaceViolation, OSError):
                continue
