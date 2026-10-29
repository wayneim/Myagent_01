"""Real scratch files, version conflicts and injected commit failures; no APIs."""

import hashlib
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock

import pytest

from myagent.core import Agent
from myagent.protocol import AssistantTurn, ToolCall
from myagent.security.permissions import PermissionEffect, PermissionEngine, PermissionRule
from myagent.security.workspace import WorkspaceResolver
from myagent.tools import file_changes, patch as patch_module
from myagent.tools.base import ExecutionContext
from myagent.tools.executor import ToolExecutor
from myagent.tools.files import EditFileTool, ReadFileTool, WriteFileTool
from myagent.tools.patch import ApplyPatchTool
from myagent.tools.registry import ToolRegistry


def digest(data):
    return hashlib.sha256(data).hexdigest()


def context(root, *extra_rules):
    policy = PermissionEngine([
        PermissionRule("read", "*", PermissionEffect.ALLOW),
        PermissionRule("edit", "*", PermissionEffect.ALLOW), *extra_rules,
    ])
    return ExecutionContext(root, policy, workspace_resolver=WorkspaceResolver(root))


def test_range_read_reports_full_raw_file_hash_in_model_visible_content(tmp_path):
    data = "第一行\r\nsecond\r\nthird\r\n".encode("utf-8")
    (tmp_path / "file.txt").write_bytes(data)
    result = ReadFileTool().execute("read", {"path": "file.txt", "start_line": 2, "end_line": 2}, context(tmp_path))
    assert not result.is_error
    assert result.metadata["sha256"] == digest(data)
    assert f"sha256={digest(data)}" in result.content
    assert "2: second" in result.content
    assert "third" not in result.content


@pytest.mark.parametrize("kind", ["edit", "write"])
def test_stale_prior_read_hash_protects_user_changes(tmp_path, kind):
    path = tmp_path / "file.txt"
    path.write_bytes(b"old\n")
    previous = ReadFileTool().execute("read", {"path": "file.txt"}, context(tmp_path)).metadata["sha256"]
    path.write_bytes(b"old\nuser change\n")  # The exact replacement target still exists.
    tool = EditFileTool() if kind == "edit" else WriteFileTool()
    args = {"path": "file.txt", "expected_hash": previous}
    args.update({"old_string": "old", "new_string": "new"} if kind == "edit" else {"content": "new"})
    result = tool.execute("change", args, context(tmp_path))
    assert result.is_error and result.metadata["kind"] == "conflict"
    assert path.read_bytes() == b"old\nuser change\n"
    assert list(tmp_path.glob(".*.myagent.tmp")) == []


def test_valid_hash_edit_preserves_raw_line_endings_and_returns_new_hash(tmp_path):
    path = tmp_path / "file.txt"
    path.write_bytes(b"old\r\nunchanged\r\n")
    result = EditFileTool().execute("edit", {
        "path": "file.txt", "old_string": "old", "new_string": "new",
        "expected_hash": digest(path.read_bytes()).upper(),
    }, context(tmp_path))
    assert not result.is_error
    assert path.read_bytes() == b"new\r\nunchanged\r\n"
    assert result.metadata["sha256"] == digest(path.read_bytes())


def test_create_only_distinguishes_missing_file_from_empty_file(tmp_path):
    tool = WriteFileTool()
    args = {"path": "new.txt", "content": "", "expected_hash": "missing"}
    created = tool.execute("create", args, context(tmp_path))
    assert not created.is_error
    refused = tool.execute("again", {**args, "content": "overwrite"}, context(tmp_path))
    assert refused.is_error and refused.metadata["kind"] == "conflict"
    assert (tmp_path / "new.txt").read_bytes() == b""
    updated = tool.execute("update", {**args, "content": "new", "expected_hash": digest(b"")}, context(tmp_path))
    assert not updated.is_error


def test_deleted_file_is_not_recreated_with_stale_hash(tmp_path):
    result = WriteFileTool().execute("write", {
        "path": "gone.txt", "content": "new", "expected_hash": digest(b"old"),
    }, context(tmp_path))
    assert result.is_error and result.metadata["kind"] == "conflict"
    assert not (tmp_path / "gone.txt").exists()


def test_unique_temporaries_do_not_touch_legacy_temp_and_are_cleaned(tmp_path, monkeypatch):
    path = tmp_path / "file.txt"
    legacy = tmp_path / ".file.txt.myagent.tmp"
    legacy.write_bytes(b"unrelated existing file")
    replacements = []
    real_replace = Path.replace

    def record_replace(source, target):
        assert source.parent == path.parent
        assert source != legacy
        replacements.append(source)
        return real_replace(source, target)

    monkeypatch.setattr(Path, "replace", record_replace)
    for text in ("one", "two"):
        result = WriteFileTool().execute(text, {"path": "file.txt", "content": text}, context(tmp_path))
        assert not result.is_error
    assert len(set(replacements)) == 2
    assert all(not temporary.exists() for temporary in replacements)
    assert legacy.read_bytes() == b"unrelated existing file"
    assert path.read_bytes() == b"two"


def test_failed_replace_keeps_original_and_cleans_temporary(tmp_path, monkeypatch):
    path = tmp_path / "file.txt"
    path.write_bytes(b"original")

    def fail_replace(*args):
        raise OSError("fixture replacement failure")

    monkeypatch.setattr(Path, "replace", fail_replace)
    result = WriteFileTool().execute("write", {"path": "file.txt", "content": "new"}, context(tmp_path))
    assert result.is_error
    assert path.read_bytes() == b"original"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["file.txt"]


def test_change_while_writing_temp_is_detected_before_replace(tmp_path, monkeypatch):
    path = tmp_path / "file.txt"
    path.write_bytes(b"original")
    real_temp = file_changes.tempfile.NamedTemporaryFile

    @contextmanager
    def mutate_during_output(*args, **kwargs):
        with real_temp(*args, **kwargs) as stream:
            yield stream
            path.write_bytes(b"user change during temporary output")

    monkeypatch.setattr(file_changes.tempfile, "NamedTemporaryFile", mutate_during_output)
    result = WriteFileTool().execute("write", {"path": "file.txt", "content": "new"}, context(tmp_path))
    assert result.is_error and result.metadata["kind"] == "conflict"
    assert path.read_bytes() == b"user change during temporary output"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["file.txt"]


@pytest.mark.parametrize("bad_operation", [
    {"kind": "delete", "path": "x"},
    {"kind": "write", "path": "x"},
    {"kind": "write", "path": "x", "content": 1},
    {"kind": "edit", "path": "x", "old_string": "", "new_string": "new"},
    {"kind": "write", "path": "x", "content": "x", "expected_hash": "invalid"},
    {"kind": "write", "path": "x", "content": "x", "unexpected": True},
    "not an operation",
])
def test_patch_schema_rejects_every_operation_before_any_approval(tmp_path, bad_operation):
    policy = Mock()
    registry = ToolRegistry()
    registry.register(ApplyPatchTool())
    result = ToolExecutor(registry, policy, ExecutionContext(tmp_path, policy)).execute(ToolCall("patch", "apply_patch", {
        "operations": [{"kind": "write", "path": "first.txt", "content": "first"}, bad_operation],
    }))
    assert result.is_error and result.metadata["kind"] == "invalid_arguments"
    policy.check.assert_not_called()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("later", [
    {"kind": "edit", "path": "existing.txt", "old_string": "absent", "new_string": "new"},
    {"kind": "edit", "path": "missing.txt", "old_string": "old", "new_string": "new"},
    {"kind": "write", "path": "existing.txt", "content": "new", "expected_hash": "missing"},
    {"kind": "write", "path": "../outside.txt", "content": "new"},
    {"kind": "write", "path": ".env", "content": "new"},
    {"kind": "write", "path": "directory", "content": "new"},
    {"kind": "write", "path": "existing.txt/child.txt", "content": "new"},
])
def test_patch_preflight_error_has_zero_writes_or_new_directories(tmp_path, later):
    (tmp_path / "existing.txt").write_bytes(b"old")
    (tmp_path / "directory").mkdir()
    result = ApplyPatchTool().execute("patch", {"operations": [
        {"kind": "write", "path": "new_directory/first.txt", "content": "first"}, later,
    ]}, context(tmp_path))
    assert result.is_error and result.metadata["phase"] == "preflight"
    assert result.metadata["modified_files"] == []
    assert (tmp_path / "existing.txt").read_bytes() == b"old"
    assert not (tmp_path / "new_directory").exists()
    assert not (tmp_path / ".env").exists()


def test_patch_detects_planned_file_directory_conflict_before_writes(tmp_path):
    result = ApplyPatchTool().execute("patch", {"operations": [
        {"kind": "write", "path": "parent", "content": "a file"},
        {"kind": "write", "path": "parent/child.txt", "content": "child"},
    ]}, context(tmp_path))
    assert result.is_error and result.metadata["phase"] == "preflight"
    assert list(tmp_path.iterdir()) == []


def test_same_file_operations_use_staged_hash_and_commit_only_final_content(tmp_path, monkeypatch):
    real_replace = Path.replace
    written = []

    def record(source, target):
        written.append(source.read_bytes())
        return real_replace(source, target)

    monkeypatch.setattr(Path, "replace", record)
    result = ApplyPatchTool().execute("patch", {"operations": [
        {"kind": "write", "path": "file.txt", "content": "one", "expected_hash": "missing"},
        {"kind": "edit", "path": "file.txt", "old_string": "one", "new_string": "two", "expected_hash": digest(b"one")},
    ]}, context(tmp_path))
    assert not result.is_error
    assert written == [b"two"]
    assert (tmp_path / "file.txt").read_bytes() == b"two"
    assert result.metadata["modified_files"] == ["file.txt"]
    assert result.metadata["hashes"]["file.txt"] == digest(b"two")


def test_second_operation_cannot_use_hash_from_before_first_staged_edit(tmp_path):
    (tmp_path / "file.txt").write_bytes(b"old")
    original_hash = digest(b"old")
    result = ApplyPatchTool().execute("patch", {"operations": [
        {"kind": "edit", "path": "file.txt", "old_string": "old", "new_string": "one", "expected_hash": original_hash},
        {"kind": "edit", "path": "file.txt", "old_string": "one", "new_string": "two", "expected_hash": original_hash},
    ]}, context(tmp_path))
    assert result.is_error and result.metadata["phase"] == "preflight"
    assert (tmp_path / "file.txt").read_bytes() == b"old"


def test_external_change_during_preflight_stops_all_tool_writes(tmp_path, monkeypatch):
    path = tmp_path / "file.txt"
    path.write_bytes(b"old")
    real_prepare = patch_module.prepare_content

    def mutate(kind, arguments, current):
        updated = real_prepare(kind, arguments, current)
        if arguments["path"] == "new/last.txt":
            path.write_bytes(b"external change")
        return updated

    monkeypatch.setattr(patch_module, "prepare_content", mutate)
    result = ApplyPatchTool().execute("patch", {"operations": [
        {"kind": "write", "path": "file.txt", "content": "new"},
        {"kind": "write", "path": "new/last.txt", "content": "last"},
    ]}, context(tmp_path))
    assert result.is_error and result.metadata["phase"] == "preflight"
    assert result.metadata["modified_files"] == []
    assert path.read_bytes() == b"external change"
    assert not (tmp_path / "new").exists()


@pytest.mark.parametrize("failure", ["io", "conflict"])
def test_commit_failure_reports_exact_modified_files_without_rollback(tmp_path, monkeypatch, failure):
    for name in ("first.txt", "second.txt", "third.txt"):
        (tmp_path / name).write_bytes(b"old")
    real_replace = Path.replace

    def injected_replace(source, target):
        if target.name == "second.txt" and failure == "io":
            raise OSError("fixture second commit failure")
        result = real_replace(source, target)
        if target.name == "first.txt" and failure == "conflict":
            (tmp_path / "second.txt").write_bytes(b"user change")
        return result

    monkeypatch.setattr(Path, "replace", injected_replace)
    result = ApplyPatchTool().execute("batch-id", {"operations": [
        {"kind": "write", "path": name, "content": "new"}
        for name in ("first.txt", "second.txt", "third.txt")
    ]}, context(tmp_path))
    assert result.call_id == "batch-id" and result.is_error
    assert result.metadata["phase"] == "commit"
    assert result.metadata["modified_files"] == ["first.txt"]
    assert result.metadata["failed_file"] == "second.txt"
    assert "first.txt" in result.content and "No rollback" in result.content
    assert (tmp_path / "first.txt").read_bytes() == b"new"
    assert (tmp_path / "second.txt").read_bytes() == (b"old" if failure == "io" else b"user change")
    assert (tmp_path / "third.txt").read_bytes() == b"old"
    assert list(tmp_path.glob(".*.myagent.tmp")) == []


def test_noop_patch_does_not_replace_or_report_modified_file(tmp_path, monkeypatch):
    (tmp_path / "file.txt").write_bytes(b"old")
    replace = Mock(side_effect=AssertionError("No-op must not replace the file"))
    monkeypatch.setattr(Path, "replace", replace)
    result = ApplyPatchTool().execute("patch", {"operations": [
        {"kind": "write", "path": "file.txt", "content": "old"},
    ]}, context(tmp_path))
    assert not result.is_error and result.metadata["modified_files"] == []
    replace.assert_not_called()


def test_interrupt_cleans_temporary_and_propagates_to_core(tmp_path, monkeypatch):
    (tmp_path / "file.txt").write_bytes(b"old")

    def interrupted_replace(*args):
        raise KeyboardInterrupt()

    monkeypatch.setattr(Path, "replace", interrupted_replace)
    with pytest.raises(KeyboardInterrupt):
        WriteFileTool().execute("write", {"path": "file.txt", "content": "new"}, context(tmp_path))
    assert sorted(path.name for path in tmp_path.iterdir()) == ["file.txt"]
    assert (tmp_path / "file.txt").read_bytes() == b"old"


def test_patch_rejects_alias_retargeted_during_same_file_operations(tmp_path, monkeypatch):
    for name in ("one.txt", "two.txt"):
        (tmp_path / name).write_bytes(b"old")
    link = tmp_path / "alias.txt"
    try:
        link.symlink_to(tmp_path / "one.txt")
    except OSError:
        pytest.skip("Creating symbolic links requires Windows privileges")
    real_prepare = patch_module.prepare_content

    def retarget(kind, arguments, current):
        updated = real_prepare(kind, arguments, current)
        link.unlink()
        link.symlink_to(tmp_path / "two.txt")
        return updated

    monkeypatch.setattr(patch_module, "prepare_content", retarget)
    result = ApplyPatchTool().execute("patch", {"operations": [
        {"kind": "write", "path": "alias.txt", "content": "first"},
        {"kind": "write", "path": "alias.txt", "content": "second"},
    ]}, context(tmp_path))
    assert result.is_error and result.metadata["phase"] == "preflight"
    assert result.metadata["kind"] == "conflict"
    assert (tmp_path / "one.txt").read_bytes() == b"old"
    assert (tmp_path / "two.txt").read_bytes() == b"old"


def test_link_alias_cannot_bypass_actual_target_edit_deny(tmp_path):
    (tmp_path / "protected.txt").write_bytes(b"old")
    try:
        (tmp_path / "alias.txt").symlink_to(tmp_path / "protected.txt")
    except OSError:
        pytest.skip("Creating symbolic links requires Windows privileges")
    policy_context = context(tmp_path, PermissionRule("edit", "protected.txt", PermissionEffect.DENY))
    registry = ToolRegistry()
    registry.register(ApplyPatchTool())
    result = ToolExecutor(registry, policy_context.permission_engine, policy_context).execute(ToolCall("patch", "apply_patch", {"operations": [
        {"kind": "write", "path": "first.txt", "content": "new"},
        {"kind": "write", "path": "alias.txt", "content": "new"},
    ]}))
    assert result.is_error
    assert not (tmp_path / "first.txt").exists()
    assert (tmp_path / "protected.txt").read_bytes() == b"old"


def test_agent_can_recover_from_stale_edit_using_model_visible_read_hash(tmp_path):
    path = tmp_path / "file.txt"
    path.write_bytes(b"old\n")
    received_results = []

    class Provider:
        step = 0

        def respond(self, system_prompt, messages, tool_definitions):
            self.step += 1
            if self.step in (1, 3):
                if self.step == 3:
                    assert messages[-1].results[0].metadata["kind"] == "conflict"
                return AssistantTurn(tool_calls=(ToolCall(f"read-{self.step}", "read_file", {"path": "file.txt"}),))
            if self.step in (2, 4):
                text = messages[-1].results[0].content
                # Providers transmit content, not ToolResult.metadata.
                expected = next(line.removeprefix("sha256=") for line in text.splitlines() if line.startswith("sha256="))
                if self.step == 2:
                    path.write_bytes(b"old\nuser addition\n")
                return AssistantTurn(tool_calls=(ToolCall(f"edit-{self.step}", "edit_file", {
                    "path": "file.txt", "old_string": "old", "new_string": "new", "expected_hash": expected,
                }),))
            received_results.extend(message.results[0] for message in messages if hasattr(message, "results"))
            return AssistantTurn("Changed the intended text and preserved the user addition.")

    execution_context = context(tmp_path)
    registry = ToolRegistry()
    for tool in (ReadFileTool(), EditFileTool()):
        registry.register(tool)
    agent = Agent(Provider(), registry, execution_context.permission_engine, execution_context)
    response = agent.run("change old to new")
    assert response.completed
    assert [result.is_error for result in received_results] == [False, True, False, False]
    assert path.read_bytes() == b"new\nuser addition\n"
