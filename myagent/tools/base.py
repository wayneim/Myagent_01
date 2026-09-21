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
    audit_events: list[dict[str, Any]] = field(default_factory=list)
    workspace_resolver: Any = None
    sandbox_backend: Any = None


class Tool(ABC):
    spec: ToolSpec

    @abstractmethod
    def execute(self, call_id: str, arguments: dict[str, Any], context: ExecutionContext) -> ToolResult:
        """Run the tool only after the agent has checked permission."""

    def resource(self, arguments: dict[str, Any]) -> str:
        return "*"
