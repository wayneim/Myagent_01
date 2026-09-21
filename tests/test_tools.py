from pathlib import Path

from myagent.security.permissions import PermissionEngine
from myagent.security.workspace import WorkspaceResolver
from myagent.tools.base import ExecutionContext
from myagent.tools.files import EditFileTool


def test_edit_requires_unique_match(tmp_path: Path) -> None:
    path = tmp_path / "example.py"
    path.write_text("x = 1\nx = 1\n", encoding="utf-8")
    context = ExecutionContext(tmp_path, PermissionEngine([]), workspace_resolver=WorkspaceResolver(tmp_path))
    result = EditFileTool().execute("call-1", {"path": "example.py", "old_string": "x = 1", "new_string": "x = 2"}, context)
    assert result.is_error
    assert path.read_text(encoding="utf-8") == "x = 1\nx = 1\n"


def test_edit_replaces_one_match(tmp_path: Path) -> None:
    path = tmp_path / "example.py"
    path.write_text("x = 1\n", encoding="utf-8")
    context = ExecutionContext(tmp_path, PermissionEngine([]), workspace_resolver=WorkspaceResolver(tmp_path))
    result = EditFileTool().execute("call-1", {"path": "example.py", "old_string": "x = 1", "new_string": "x = 2"}, context)
    assert not result.is_error
    assert path.read_text(encoding="utf-8") == "x = 2\n"
