"""Read-only Git observation tools."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .base import ExecutionContext, Tool, ToolSpec
from myagent.protocol import ToolResult


class GitTool(Tool):
    def __init__(self, name: str, command: list[str], description: str) -> None:
        self.command = command
        self.spec = ToolSpec(name, description, {"type": "object", "properties": {}}, "read", True, True)

    def execute(self, call_id: str, arguments: dict[str, Any], context: ExecutionContext) -> ToolResult:
        try:
            completed = subprocess.run(self.command, cwd=context.workspace, capture_output=True, text=True, timeout=20, check=False)
            output = (completed.stdout + completed.stderr).strip()
            return ToolResult(call_id, output[: context.max_output_chars], completed.returncode != 0)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return ToolResult(call_id, f"git failed: {exc}", True)


def git_status() -> GitTool:
    return GitTool("git_status", ["git", "status", "--short", "--branch"], "Show repository status.")


def git_diff() -> GitTool:
    return GitTool("git_diff", ["git", "diff", "--"], "Show unstaged repository changes.")
