"""Provider defaults and factories shared by configuration and runtime."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import TYPE_CHECKING    # 运行时为False，既避免循环导入，又能静态类型检查

from myagent.provider import LLMProvider

if TYPE_CHECKING:
    from myagent.config import AgentConfig


@dataclass(frozen=True)     # frozen表示一旦创建不可变
class ProviderSpec:
    name: str
    env_prefix: str
    default_model: str
    default_base_url: str
    factory_path: str

    @property               # 把方法伪装成只读属性，调用时不用加括号
    def api_key_env(self) -> str:
        return f"{self.env_prefix}_API_KEY"


class ProviderRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, ProviderSpec] = {}

    def register(self, spec: ProviderSpec) -> None:
        if not spec.name or spec.name != spec.name.strip().lower():
            raise ValueError("Provider name must be nonempty, lowercase and trimmed")
        if spec.name in self._specs:
            raise ValueError(f"Provider already registered: {spec.name}")
        self._specs[spec.name] = spec

    def get(self, name: str) -> ProviderSpec:
        if name not in self._specs:
            raise ValueError(f"Unsupported provider: {name}. Choose {', '.join(self._specs)}.")
        return self._specs[name]

    def create(self, config: AgentConfig) -> LLMProvider:
        spec = self.get(config.model.provider)
        key = (config.api_key or "").strip()
        if not key:
            choices = "\n".join(
                f"  MYAGENT_PROVIDER={item.name}; {item.api_key_env}=<your-api-key>"
                for item in self._specs.values()
            )
            raise ValueError(
                f"需要配置模型：所选服务商 '{spec.name}' 缺少环境变量 {spec.api_key_env}。\n"
                f"请在 .env 文件或系统环境变量中配置（选择一个服务商）：\n{choices}\n"
                f"可选配置：{spec.env_prefix}_MODEL 和 {spec.env_prefix}_BASE_URL。\n"
                "服务商不会自动切换。"
            )
        for field, value in (("MODEL", config.model.model), ("BASE_URL", config.model.base_url)):
            if not value.strip():
                raise ValueError(f"{spec.env_prefix}_{field} must not be empty")
        module_name, attribute = spec.factory_path.rsplit(":", 1)
        factory = getattr(import_module(module_name), attribute)
        return factory(key, config.model.base_url.strip(), config.model.model.strip())

# 注册可用的厂商，具体使用哪个根据配置中的MYAGENT_PROVIDER决定
provider_registry = ProviderRegistry()
provider_registry.register(ProviderSpec(
    "minimax", "MINIMAX", "MiniMax-M3", "https://api.minimax.cn/anthropic",
    "myagent.providers.minimax:MiniMaxProvider",
))
provider_registry.register(ProviderSpec(
    "qwen", "QWEN", "qwen-plus", "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "myagent.providers.qwen:QwenProvider",
))
