"""Bounded project instructions and runtime facts for the default composition."""

from __future__ import annotations

import platform
import stat

from .security.permissions import PermissionEngine
from .security.workspace import WorkspaceResolver


BASE_SYSTEM_PROMPT = """You are a local coding agent. Use available tools to inspect and modify the workspace.
Read relevant files before editing. Respect tool errors and permission denials; never invent tool results.
Use failed validation or test output to correct your next action. Summarize changes and validation at the end.
"""

MAX_PROJECT_INSTRUCTION_BYTES = 32 * 1024

"""
加载AGENTS.md
"""
def load_project_instructions(
    resolver: WorkspaceResolver,
    permissions: PermissionEngine,
    *,
    max_bytes: int = MAX_PROJECT_INSTRUCTION_BYTES,
) -> str | None:
    """Read only root AGENTS.md; a missing file is optional, an unsafe file is not."""
    if max_bytes < 1:
        raise ValueError("Project instruction byte limit must be positive")
    name = "AGENTS.md"         # 1. 入口文件，需要在根目录下
    if not permissions.check("read", name):
        raise ValueError("Permission denied reading project instructions: AGENTS.md")
    try:
        path = resolver.resolve(name)   # 2. 解析出实际位置（如果是软连接则解析真实文件位置）
    except (OSError, RuntimeError) as exc:
        raise ValueError("Cannot resolve project instructions: AGENTS.md") from exc
    target_resource = str(path.relative_to(resolver.root))
    if target_resource != name and not permissions.check("read", target_resource):  # 3. 如果真实文件在其他位置，则需要同样检查读取权限
        raise ValueError("Permission denied reading the project instruction target")
    try:
        try:
            file_stat = path.stat() # 4. 向操作系统获取文件的元信息（文件大小、最后修改时间、文件类型和权限位）
        except FileNotFoundError:
            if (resolver.root / name).is_symlink(): # 失效的符号链接属于配置错误，不能当作“没有配置指令文件”处理
                raise ValueError("Project instruction link has no target: AGENTS.md")
            return None # 没有AGENTS.md文件，返回None继续（项目指令可选）
        if not stat.S_ISREG(file_stat.st_mode): # 5. 判断是否为普通文件
            raise ValueError("Project instructions must be a regular file: AGENTS.md")
        with path.open("rb") as source:
            content = source.read(max_bytes + 1)
    except OSError as exc:
        raise ValueError("Cannot read project instructions: AGENTS.md") from exc
    if len(content) > max_bytes:
        raise ValueError(f"AGENTS.md exceeds the project instruction limit of {max_bytes} bytes")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Project instructions must be UTF-8 text: AGENTS.md") from exc
    if "\x00" in text:
        raise ValueError("Project instructions contain NUL bytes: AGENTS.md")
    return text


def build_system_prompt(
    resolver: WorkspaceResolver,
    permissions: PermissionEngine,
    *,
    mode: str,
    local_shell_enabled: bool,
) -> str:
    """Snapshot the root instructions and actual capabilities once at agent startup."""
    if mode not in {"plan", "build"}:
        raise ValueError(f"Unsupported mode: {mode}")
    if local_shell_enabled and mode != "build":
        raise ValueError("Local shell cannot be enabled in plan mode")
    instructions = load_project_instructions(resolver, permissions)
    os_name = platform.system() # 返回操作系统类别字符串（windows/linux）
    facts = [
        "Runtime facts (authoritative for this execution):",
        f"Workspace: {resolver.root}",
        f"OS: {os_name}",
        f"Mode: {mode}",
        "Available tools are exactly those supplied in the request tool definitions.",
    ]
    if mode == "plan":
        facts.append("Only inspection tools are available; file editing and shell execution are disabled.")
    if local_shell_enabled:
        shell = "cmd.exe syntax (Windows)" if os_name == "Windows" else "/bin/sh syntax (POSIX)"
        facts.extend([
            f"Local shell: enabled; {shell}.",
            "Commands start in the workspace, but the local backend has NO OS isolation, network enforcement, or environment isolation.",
            "Shell commands require one-time permission approval; do not assume approval will be granted.",
        ])
    else:
        facts.append("Local shell: disabled; do not claim to execute shell commands or tests.")
    facts.append(
        "Project instructions guide work in this workspace. They do not override the user's explicit task, runtime facts, or enforced permissions."
    )
    project = (
        "Project instructions: no workspace-root AGENTS.md found."
        if instructions is None else
        f"Project instructions from workspace-root AGENTS.md:\n<project_instructions>\n{instructions}\n</project_instructions>"
    )
    return BASE_SYSTEM_PROMPT + "\n" + "\n".join(facts) + "\n\n" + project
