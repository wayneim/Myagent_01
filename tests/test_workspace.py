from pathlib import Path

import pytest

from myagent.security.workspace import WorkspaceResolver, WorkspaceViolation


def test_workspace_rejects_escape(tmp_path: Path) -> None:
    resolver = WorkspaceResolver(tmp_path)
    with pytest.raises(WorkspaceViolation):
        resolver.resolve("../outside.txt")


def test_workspace_rejects_env_file(tmp_path: Path) -> None:
    resolver = WorkspaceResolver(tmp_path)
    with pytest.raises(WorkspaceViolation):
        resolver.resolve(".env")
