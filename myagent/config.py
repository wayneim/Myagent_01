"""Configuration loaded from explicit values and environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModelProfile:
    provider: str
    model: str
    base_url: str
    supports_native_tools: bool = True
    supports_streaming: bool = True
    supports_parallel_tools: bool = True
    text_tool_protocol: str | None = None


@dataclass(frozen=True)
class AgentConfig:
    workspace: Path
    model: ModelProfile
    api_key: str | None
    max_steps: int = 20
    max_tool_output_chars: int = 20_000
    network_mode: str = "deny"

    @classmethod
    def from_environment(cls, workspace: Path | None = None) -> "AgentConfig":
        resolved_workspace = (workspace or Path(os.getenv("MYAGENT_WORKSPACE", "."))).resolve()
        return cls(
            workspace=resolved_workspace,
            api_key=os.getenv("MINIMAX_API_KEY"),
            network_mode=os.getenv("MYAGENT_NETWORK_MODE", "deny"),
            model=ModelProfile(
                provider="minimax",
                model=os.getenv("MINIMAX_MODEL", "MiniMax-M3"),
                base_url=os.getenv("MINIMAX_BASE_URL", "https://api.minimax.cn/anthropic"),
            ),
        )
