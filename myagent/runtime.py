"""Default runtime composition for the CLI and embedding applications."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .config import AgentConfig
from .core import Agent
from .prompting import build_system_prompt
from .providers.registry import provider_registry
from .security.permissions import ApprovalHandler, PermissionEffect, PermissionEngine, PermissionRule
from .security.sandbox import ProcessResult
from .security.workspace import WorkspaceResolver
from .tools.base import ExecutionContext
from .tools.files import EditFileTool, GlobTool, GrepTool, ReadFileTool, WriteFileTool
from .tools.git import git_diff, git_status
from .tools.patch import ApplyPatchTool
from .tools.registry import ToolRegistry
from .tools.shell import ShellTool


class LocalProcessBackend:      # 未沙箱化shell后端，兜底，所有调用都需要经过权限审批
    """Unsandboxed fallback. Shell calls must receive explicit approval."""

    def run(self, command: str, workspace: Path, timeout_seconds: int) -> ProcessResult:
        # cwd默认在workspace下工作，但是shell=True允许任意语法，因此真正限制需要权限审批
        completed = subprocess.run(command, cwd=workspace, shell=True, capture_output=True, text=True, timeout=timeout_seconds)
        return ProcessResult(completed.returncode, completed.stdout, completed.stderr, False)


def build_agent(config: AgentConfig, event_handler=None, mode: str = "build", approval_handler: ApprovalHandler | None = None) -> Agent:
    if mode not in {"plan", "build"}:
        raise ValueError(f"Unsupported mode: {mode}")
    if not config.workspace.is_dir():
        raise ValueError(f"Workspace directory does not exist: {config.workspace}")
    resolver = WorkspaceResolver(config.workspace)
    rules = [
        PermissionRule("read", "*", PermissionEffect.ALLOW),
    ]
    if mode == "build":
        rules.append(PermissionRule("edit", "*", PermissionEffect.ASK))
        rules.append(PermissionRule("shell", "*", PermissionEffect.ASK))
    permissions = PermissionEngine(rules, approval_handler=approval_handler)
    local_shell_enabled = config.allow_unsandboxed_shell and mode == "build"
    system_prompt = build_system_prompt(
        resolver, permissions, mode=mode, local_shell_enabled=local_shell_enabled,
    )
    provider = provider_registry.create(config)
    context = ExecutionContext(
        config.workspace,
        permissions,
        max_output_chars=config.max_tool_output_chars,
        workspace_resolver=resolver,
        sandbox_backend=LocalProcessBackend() if local_shell_enabled else None,      # 本地后端没有 OS 隔离，且仅在 build 模式显式启用。
    )
    registry = ToolRegistry()
    for tool in (ReadFileTool(), GlobTool(), GrepTool(), EditFileTool(), WriteFileTool(), ApplyPatchTool(), git_status(), git_diff()):
        registry.register(tool)
    if local_shell_enabled:
        registry.register(ShellTool())
    if mode == "plan":
        registry = ToolRegistry()
        for tool in (ReadFileTool(), GlobTool(), GrepTool(), git_status(), git_diff()):
            registry.register(tool)
    return Agent(provider, registry, permissions, context, system_prompt=system_prompt, event_handler=event_handler)
