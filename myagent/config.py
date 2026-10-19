"""Configuration loaded from explicit values and environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from .providers.registry import provider_registry


@dataclass(frozen=True)
class ModelProfile:
    provider: str
    model: str
    base_url: str


@dataclass(frozen=True)
class AgentConfig:
    workspace: Path
    model: ModelProfile
    api_key: str | None
    max_steps: int = 20
    max_tool_output_chars: int = 20_000
    allow_unsandboxed_shell: bool = False   # 显式启用本地未沙箱化 Shell

    @classmethod
    def from_environment(cls, workspace: Path | None = None) -> "AgentConfig":
        load_dotenv()
        resolved_workspace = (workspace or Path(os.getenv("MYAGENT_WORKSPACE", "."))).resolve()
        provider = os.getenv("MYAGENT_PROVIDER", "minimax").strip().lower()
        spec = provider_registry.get(provider)
        api_key = os.getenv(spec.api_key_env)
        model = os.getenv(f"{spec.env_prefix}_MODEL", spec.default_model)
        base_url = os.getenv(f"{spec.env_prefix}_BASE_URL", spec.default_base_url)
        return cls(
            workspace=resolved_workspace,
            api_key=api_key,
            model=ModelProfile(
                provider=provider,
                model=model,
                base_url=base_url,
            ),
        )
