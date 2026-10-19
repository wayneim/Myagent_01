from pathlib import Path
from dataclasses import replace
from unittest.mock import patch

import pytest

from myagent.config import AgentConfig, ModelProfile
from myagent.runtime import build_agent


def _config(tmp_path: Path) -> AgentConfig:
    return AgentConfig(tmp_path, ModelProfile("minimax", "test", "http://localhost"), "test-key")


def test_plan_mode_exposes_read_only_tools(tmp_path: Path) -> None:
    agent = build_agent(_config(tmp_path), mode="plan")
    names = {definition["name"] for definition in agent.tools.definitions()}
    assert names == {"read_file", "glob", "grep", "git_status", "git_diff"}


def test_build_mode_exposes_edits_but_shell_is_opt_in(tmp_path: Path) -> None:
    agent = build_agent(_config(tmp_path), mode="build")
    names = {definition["name"] for definition in agent.tools.definitions()}
    assert {"edit_file", "write_file", "apply_patch"} <= names
    assert "bash" not in names


def test_local_shell_requires_explicit_opt_in_and_each_command_approval(tmp_path):
    with patch("myagent.providers.minimax.MiniMaxProvider"):
        agent = build_agent(replace(_config(tmp_path), allow_unsandboxed_shell=True))
    assert agent.tools.get("bash") is not None
    assert agent.execution_context.sandbox_backend is not None
    assert not agent.permission_engine.check("shell", "git status & echo example")


def test_unknown_provider_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="Unsupported provider"):
        build_agent(replace(_config(tmp_path), model=ModelProfile("typo", "test", "http://localhost")))
