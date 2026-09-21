from pathlib import Path

from myagent.config import AgentConfig, ModelProfile
from myagent.runtime import build_agent


def _config(tmp_path: Path) -> AgentConfig:
    return AgentConfig(tmp_path, ModelProfile("test", "test", "http://localhost"), "test-key")


def test_plan_mode_exposes_read_only_tools(tmp_path: Path) -> None:
    agent = build_agent(_config(tmp_path), mode="plan")
    names = {definition["name"] for definition in agent.tools.definitions()}
    assert names == {"read_file", "glob", "grep", "git_status", "git_diff"}


def test_build_mode_exposes_edit_and_shell_tools(tmp_path: Path) -> None:
    agent = build_agent(_config(tmp_path), mode="build")
    names = {definition["name"] for definition in agent.tools.definitions()}
    assert {"edit_file", "write_file", "apply_patch", "bash"} <= names
