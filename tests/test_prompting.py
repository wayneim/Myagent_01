"""Prompt assembly tests use only scratch instructions and fake providers."""

from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from myagent.config import AgentConfig, ModelProfile
from myagent.cli.repl import main
from myagent.prompting import MAX_PROJECT_INSTRUCTION_BYTES, build_system_prompt, load_project_instructions
from myagent.protocol import AssistantTurn, ToolCall
from myagent.runtime import build_agent
from myagent.security.permissions import PermissionEffect, PermissionEngine, PermissionRule
from myagent.security.workspace import WorkspaceResolver, WorkspaceViolation


def permissions(*extra):
    return PermissionEngine([PermissionRule("read", "*", PermissionEffect.ALLOW), *extra])


def test_only_workspace_root_instructions_are_loaded(tmp_path):
    (tmp_path / "AGENTS.md").write_text("parent instructions", encoding="utf-8")
    workspace = tmp_path / "project"
    workspace.mkdir()
    (workspace / "nested").mkdir()
    (workspace / "nested" / "AGENTS.md").write_text("nested instructions", encoding="utf-8")
    (workspace / ".env").write_text("FAKE_SECRET=must-not-load", encoding="utf-8")
    resolver = WorkspaceResolver(workspace)
    prompt = build_system_prompt(resolver, permissions(), mode="build", local_shell_enabled=False)
    assert "no workspace-root AGENTS.md found" in prompt
    for text in ("parent instructions", "nested instructions", "must-not-load"):
        assert text not in prompt
    (workspace / "AGENTS.md").write_text("root instructions", encoding="utf-8")
    prompt = build_system_prompt(resolver, permissions(), mode="build", local_shell_enabled=False)
    assert "root instructions" in prompt
    assert "parent instructions" not in prompt
    assert "nested instructions" not in prompt


@pytest.mark.parametrize("content", [b"", b"test instructions", b"\xef\xbb\xbfUTF-8 BOM", "使用项目规范".encode("utf-8")])
def test_utf8_instructions_are_loaded_without_changing_content(tmp_path, content):
    (tmp_path / "AGENTS.md").write_bytes(content)
    assert load_project_instructions(WorkspaceResolver(tmp_path), permissions()) == content.decode("utf-8-sig")


def test_instruction_limit_counts_bytes_and_does_not_silently_truncate(tmp_path):
    (tmp_path / "AGENTS.md").write_text("你好", encoding="utf-8")
    resolver = WorkspaceResolver(tmp_path)
    assert load_project_instructions(resolver, permissions(), max_bytes=6) == "你好"
    with pytest.raises(ValueError, match="limit of 5 bytes"):
        load_project_instructions(resolver, permissions(), max_bytes=5)


@pytest.mark.parametrize("content,error", [(b"\xff", "UTF-8"), (b"text\x00text", "NUL")])
def test_malformed_instructions_are_not_included(tmp_path, content, error):
    (tmp_path / "AGENTS.md").write_bytes(content)
    with pytest.raises(ValueError, match=error):
        load_project_instructions(WorkspaceResolver(tmp_path), permissions())


def test_instruction_read_obeys_permission_engine(tmp_path):
    (tmp_path / "AGENTS.md").write_text("private instructions", encoding="utf-8")
    denied = permissions(PermissionRule("read", "AGENTS.md", PermissionEffect.DENY))
    with patch.object(Path, "open") as read:
        with pytest.raises(ValueError, match="Permission denied"):
            load_project_instructions(WorkspaceResolver(tmp_path), denied)
        read.assert_not_called()


def test_instruction_directory_is_rejected(tmp_path):
    (tmp_path / "AGENTS.md").mkdir()
    with pytest.raises(ValueError, match="regular file"):
        load_project_instructions(WorkspaceResolver(tmp_path), permissions())


def test_instruction_io_error_has_actionable_message(tmp_path):
    (tmp_path / "AGENTS.md").write_text("test", encoding="utf-8")
    with patch.object(Path, "open", side_effect=PermissionError("fixture")):
        with pytest.raises(ValueError, match="Cannot read project instructions"):
            load_project_instructions(WorkspaceResolver(tmp_path), permissions())


def symlink_or_skip(link, target):
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"Symbolic link creation is unavailable: {exc}")


@pytest.mark.parametrize("target_kind", ["outside", "sensitive", "denied", "missing"])
def test_instruction_links_cannot_bypass_boundaries_or_permissions(tmp_path, target_kind):
    workspace = tmp_path / "project"
    workspace.mkdir()
    resolver = WorkspaceResolver(workspace)
    if target_kind == "outside":
        target = tmp_path / "outside.txt"
    elif target_kind == "sensitive":
        target = workspace / ".env"
    else:
        target = workspace / "target.txt"
    if target_kind != "missing":
        target.write_text("must not load", encoding="utf-8")
    symlink_or_skip(workspace / "AGENTS.md", target)
    policy = permissions(PermissionRule("read", "target.txt", PermissionEffect.DENY)) if target_kind == "denied" else permissions()
    with pytest.raises((ValueError, WorkspaceViolation)):
        load_project_instructions(resolver, policy)


@pytest.mark.parametrize("os_name,mode,shell", [
    ("Windows", "plan", False), ("Windows", "build", False),
    ("Windows", "build", True), ("Linux", "build", True),
])
def test_runtime_facts_match_available_capabilities(tmp_path, os_name, mode, shell):
    with patch("myagent.prompting.platform.system", return_value=os_name):
        prompt = build_system_prompt(WorkspaceResolver(tmp_path), permissions(), mode=mode, local_shell_enabled=shell)
    assert f"Workspace: {tmp_path.resolve()}" in prompt
    assert f"OS: {os_name}" in prompt
    assert f"Mode: {mode}" in prompt
    assert "do not override the user's explicit task, runtime facts, or enforced permissions" in prompt
    if shell:
        assert "Local shell: enabled" in prompt
        assert ("cmd.exe" if os_name == "Windows" else "/bin/sh") in prompt
        assert "NO OS isolation" in prompt
        assert "one-time permission approval" in prompt
    else:
        assert "Local shell: disabled" in prompt
        assert "Local shell: enabled" not in prompt
    if mode == "plan":
        assert "Only inspection tools" in prompt


@pytest.mark.parametrize("mode,opt_in", [("plan", False), ("plan", True), ("build", False), ("build", True)])
def test_runtime_sends_project_prompt_on_every_model_turn(tmp_path, mode, opt_in):
    (tmp_path / "AGENTS.md").write_text("Use fixture project conventions.", encoding="utf-8")
    (tmp_path / "sample.txt").write_text("fixture", encoding="utf-8")
    config = AgentConfig(tmp_path, ModelProfile("qwen", "fixture", "http://localhost"), "fixture")
    config = replace(config, allow_unsandboxed_shell=opt_in)
    provider = Mock()
    provider.respond.side_effect = [
        AssistantTurn(tool_calls=(ToolCall("read", "read_file", {"path": "sample.txt"}),)),
        AssistantTurn("done"), AssistantTurn("followup"),
    ]
    with patch("myagent.runtime.provider_registry.create", return_value=provider):
        agent = build_agent(config, mode=mode)
    response = agent.run("read sample")
    assert agent.run("follow up", session_id=response.session_id).completed
    assert provider.respond.call_count == 3
    prompts = [call.args[0] for call in provider.respond.call_args_list]
    assert all(prompt == agent.system_prompt for prompt in prompts)
    assert "Use fixture project conventions." in prompts[0]
    assert f"Mode: {mode}" in prompts[0]
    shell_available = mode == "build" and opt_in
    assert ("Local shell: enabled" in prompts[0]) == shell_available
    assert (agent.tools.get("bash") is not None) == shell_available
    assert (agent.execution_context.sandbox_backend is not None) == shell_available


def test_oversized_project_instructions_fail_before_provider_creation(tmp_path):
    (tmp_path / "AGENTS.md").write_bytes(b"x" * (MAX_PROJECT_INSTRUCTION_BYTES + 1))
    config = AgentConfig(tmp_path, ModelProfile("qwen", "fixture", "http://localhost"), "fixture")
    with patch("myagent.runtime.provider_registry.create") as create:
        with pytest.raises(ValueError, match="exceeds"):
            build_agent(config)
        create.assert_not_called()


def test_instruction_resolution_failure_is_a_startup_error(tmp_path):
    resolver = WorkspaceResolver(tmp_path)
    with patch.object(resolver, "resolve", side_effect=OSError("fixture resolution failure")):
        with pytest.raises(ValueError, match="Cannot resolve project instructions"):
            load_project_instructions(resolver, permissions())


def test_json_startup_instruction_error_is_structured(tmp_path, monkeypatch, capsys):
    import json

    (tmp_path / "AGENTS.md").write_bytes(b"\xff")
    monkeypatch.setattr("sys.argv", ["myagent", "--json-events", "task"])
    config = AgentConfig(tmp_path, ModelProfile("qwen", "fixture", "http://localhost"), "fixture")
    with (
        patch("myagent.cli.repl.AgentConfig.from_environment", return_value=config),
        patch("myagent.runtime.provider_registry.create") as create,
    ):
        assert main() == 2
        create.assert_not_called()
    event = json.loads(capsys.readouterr().out)
    assert event["type"] == "error"
    assert "UTF-8" in event["data"]["message"]
