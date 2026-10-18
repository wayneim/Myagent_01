from unittest.mock import Mock

import pytest

from myagent.protocol import ToolCall, ToolResult
from myagent.security.permissions import PermissionEffect, PermissionEngine, PermissionRule
from myagent.tools.base import ExecutionContext
from myagent.tools.executor import ToolExecutor
from myagent.tools.files import ReadFileTool
from myagent.tools.patch import ApplyPatchTool
from myagent.tools.registry import ToolRegistry


@pytest.mark.parametrize("arguments", [{}, {"path": 42}, {"path": "file", "start_line": "first"}, []])
def test_schema_rejects_bad_arguments_before_permission_or_execution(tmp_path, arguments):
    permissions = Mock()
    tool = ReadFileTool()
    tool.execute = Mock()
    registry = ToolRegistry()
    registry.register(tool)
    result = ToolExecutor(registry, permissions, ExecutionContext(tmp_path, permissions)).execute(ToolCall("one", "read_file", arguments))
    assert result.is_error
    assert result.metadata["kind"] == "invalid_arguments"
    permissions.check.assert_not_called()
    tool.execute.assert_not_called()


def test_parse_error_never_executes_tool(tmp_path):
    registry = ToolRegistry()
    tool = ReadFileTool()
    tool.execute = Mock()
    registry.register(tool)
    permissions = Mock()
    result = ToolExecutor(registry, permissions, ExecutionContext(tmp_path, permissions)).execute(ToolCall("one", "read_file", {}, parse_error="Invalid JSON"))
    assert result.is_error
    assert result.content == "Invalid JSON"
    tool.execute.assert_not_called()


def test_compound_tool_checks_all_file_permissions_before_any_write(tmp_path):
    registry = ToolRegistry()
    registry.register(ApplyPatchTool())
    permissions = PermissionEngine([
        PermissionRule("edit", "*", PermissionEffect.ALLOW),
        PermissionRule("edit", "protected.txt", PermissionEffect.DENY),
    ])
    context = ExecutionContext(tmp_path, permissions)
    result = ToolExecutor(registry, permissions, context).execute(ToolCall("one", "apply_patch", {"operations": [
        {"kind": "write", "path": "allowed.txt", "content": "hello"},
        {"kind": "write", "path": "protected.txt", "content": "no"},
    ]}))
    assert result.is_error
    assert not (tmp_path / "allowed.txt").exists()
    assert not (tmp_path / "protected.txt").exists()


def test_executor_limits_custom_tool_output(tmp_path):
    tool = ReadFileTool()
    tool.execute = Mock(return_value=ToolResult("one", "a" * 100))
    registry = ToolRegistry()
    registry.register(tool)
    permissions = PermissionEngine([PermissionRule("read", "*", PermissionEffect.ALLOW)])
    result = ToolExecutor(registry, permissions, ExecutionContext(tmp_path, permissions, max_output_chars=10)).execute(ToolCall("one", "read_file", {"path": "unused"}))
    assert result.content == "a" * 10
    assert result.metadata["truncated"]
