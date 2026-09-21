"""Default runtime composition for the CLI and embedding applications."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .config import AgentConfig
from .core import Agent
from .providers.minimax import MiniMaxProvider
from .security.permissions import ApprovalHandler, PermissionEffect, PermissionEngine, PermissionRule
from .security.sandbox import ProcessResult
from .security.workspace import WorkspaceResolver
from .tools.base import ExecutionContext
from .tools.files import EditFileTool, GlobTool, GrepTool, ReadFileTool, WriteFileTool
from .tools.git import git_diff, git_status
from .tools.patch import ApplyPatchTool
from .tools.registry import ToolRegistry
from .tools.shell import ShellTool


class LocalProcessBackend:
    """Unsandboxed fallback. Shell calls must receive explicit approval."""

    def run(self, command: str, workspace: Path, timeout_seconds: int) -> ProcessResult:
        completed = subprocess.run(command, cwd=workspace, shell=True, capture_output=True, text=True, timeout=timeout_seconds)
        return ProcessResult(completed.returncode, completed.stdout, completed.stderr, False)


def build_agent(config: AgentConfig, event_handler=None, mode: str = "build", approval_handler: ApprovalHandler | None = None) -> Agent:
    if mode not in {"plan", "build"}:
        raise ValueError(f"Unsupported mode: {mode}")
    resolver = WorkspaceResolver(config.workspace)
    rules = [
        PermissionRule("read", "*", PermissionEffect.ALLOW),
        PermissionRule("shell", "git status*", PermissionEffect.ALLOW),
        PermissionRule("shell", "git diff*", PermissionEffect.ALLOW),
    ]
    if mode == "build":
        rules.append(PermissionRule("edit", "*", PermissionEffect.ASK))
        rules.append(PermissionRule("shell", "*", PermissionEffect.ASK))
    permissions = PermissionEngine(rules, approval_handler=approval_handler)
    context = ExecutionContext(
        config.workspace,
        permissions,
        max_output_chars=config.max_tool_output_chars,
        workspace_resolver=resolver,
        sandbox_backend=LocalProcessBackend(),
    )
    registry = ToolRegistry()
    for tool in (ReadFileTool(), GlobTool(), GrepTool(), EditFileTool(), WriteFileTool(), ApplyPatchTool(), git_status(), git_diff(), ShellTool()):
        registry.register(tool)
    provider = MiniMaxProvider(config.api_key or "", config.model.base_url, config.model.model)
    if mode == "plan":
        registry = ToolRegistry()
        for tool in (ReadFileTool(), GlobTool(), GrepTool(), git_status(), git_diff()):
            registry.register(tool)
    return Agent(provider, registry, permissions, context, event_handler=event_handler)
