from pathlib import Path
import pytest

from myagent.security.permissions import PermissionEffect, PermissionEngine, PermissionRule
from myagent.security.workspace import WorkspaceResolver
from myagent.tools.base import ExecutionContext
from myagent.tools.files import EditFileTool, GlobTool, GrepTool


def read_permissions():
    return PermissionEngine([PermissionRule('read', '*', PermissionEffect.ALLOW)])


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


def test_search_uses_sensitive_path_checks_and_ignores_binary_files(tmp_path):
    (tmp_path / '.env').write_text('SENTINEL=secret', encoding='utf-8')
    (tmp_path / '.env.private').mkdir()
    (tmp_path / '.env.private' / 'nested.txt').write_text('SENTINEL=secret', encoding='utf-8')
    (tmp_path / 'visible.txt').write_text('SENTINEL=public', encoding='utf-8')
    (tmp_path / 'binary.dat').write_bytes(b'\x00SENTINEL=binary')
    context = ExecutionContext(tmp_path, read_permissions())
    grep = GrepTool().execute('grep', {'pattern': 'SENTINEL'}, context)
    glob = GlobTool().execute('glob', {'pattern': '**/*'}, context)
    assert 'public' in grep.content
    assert 'secret' not in grep.content
    assert 'binary' not in grep.content
    assert '.env' not in glob.content


@pytest.mark.parametrize('tool,args', [(GlobTool(), {'pattern': '../*'}), (GrepTool(), {'pattern': 'x', 'glob': '../*'})])
def test_search_rejects_path_escape(tmp_path, tool, args):
    result = tool.execute('one', args, ExecutionContext(tmp_path, read_permissions()))
    assert result.is_error


def test_invalid_regex_is_a_tool_result(tmp_path):
    result = GrepTool().execute('one', {'pattern': '['}, ExecutionContext(tmp_path, read_permissions()))
    assert result.is_error
    assert 'grep failed' in result.content


def test_search_result_limits_stop_collection(tmp_path):
    for index in range(5):
        (tmp_path / f'{index}.txt').write_text('match\nmatch\n', encoding='utf-8')
    context = ExecutionContext(tmp_path, read_permissions(), max_search_results=2)
    grep = GrepTool().execute('one', {'pattern': 'match'}, context)
    glob = GlobTool().execute('two', {'pattern': '*.txt'}, context)
    assert len(grep.content.splitlines()) == 2
    assert len(glob.content.splitlines()) == 2
    assert grep.metadata['truncated'] and glob.metadata['truncated']


def test_search_does_not_follow_file_link_outside_workspace(tmp_path):
    root = tmp_path / 'workspace'
    root.mkdir()
    outside = tmp_path / 'outside.txt'
    outside.write_text('SENTINEL=outside', encoding='utf-8')
    try:
        (root / 'link.txt').symlink_to(outside)
    except OSError:
        pytest.skip('Creating symbolic links requires Windows privileges')
    context = ExecutionContext(root, read_permissions())
    assert 'outside' not in GrepTool().execute('one', {'pattern': 'SENTINEL'}, context).content
    assert 'link.txt' not in GlobTool().execute('two', {'pattern': '*'}, context).content


def test_search_respects_deny_rules_for_individual_matches(tmp_path):
    (tmp_path / 'public.txt').write_text('match public', encoding='utf-8')
    (tmp_path / 'private.txt').write_text('match private', encoding='utf-8')
    permissions = PermissionEngine([
        PermissionRule('read', '*', PermissionEffect.ALLOW),
        PermissionRule('read', 'private.txt', PermissionEffect.DENY),
    ])
    context = ExecutionContext(tmp_path, permissions)
    assert 'private' not in GrepTool().execute('one', {'pattern': 'match'}, context).content
    assert 'private.txt' not in GlobTool().execute('two', {'pattern': '*'}, context).content
    assert 'public' in GrepTool().execute('three', {'pattern': 'match'}, context).content
