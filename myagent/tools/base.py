"""Tool extension contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from myagent.protocol import ToolResult


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]      # 要按照json scheme进行编写，方便校验
    action: str                     # 工具执行时需要检查的权限类别，例如 "read"、"edit"、"shell"


@dataclass
class ExecutionContext:
    workspace: Any
    permission_engine: Any
    cancellation_requested: Any = lambda: False     # 查询“当前任务是否已被请求取消”，暂时没有实际作用
    max_output_chars: int = 20_000
    audit_events: list[dict[str, Any]] = field(default_factory=list) # [] 会让所有实例共享同一个列表，default_factory 确保每个实例创建时都生成新的空列表。
    workspace_resolver: Any = None
    sandbox_backend: Any = None
    max_search_files: int = 1_000
    max_search_results: int = 200
    max_search_file_bytes: int = 2_000_000


class Tool(ABC):
    spec: ToolSpec

    @abstractmethod
    def execute(self, call_id: str, arguments: dict[str, Any], context: ExecutionContext) -> ToolResult:
        """Run the tool only after the agent has checked permission."""

    def resource(self, arguments: dict[str, Any]) -> str:       # 本次工具调用准备操作哪些资源，供权限系统在执行前检查
        return "*"

    def resources(self, arguments: dict[str, Any]) -> list[str]:
        """Compound tools must expose every resource for individual authorization."""
        return [self.resource(arguments)]
