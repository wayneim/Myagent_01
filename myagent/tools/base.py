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
    parameters: dict[str, Any]
    action: str
    read_only: bool = False
    supports_parallel: bool = False


@dataclass
class ExecutionContext:
    workspace: Any
    permission_engine: Any
    cancellation_requested: Any = lambda: False
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

    def resource(self, arguments: dict[str, Any]) -> str:
        return "*"

    def resources(self, arguments: dict[str, Any]) -> list[str]:
        """Compound tools must expose every resource for individual authorization."""
        return [self.resource(arguments)]
