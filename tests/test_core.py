from pathlib import Path

from myagent.core import Agent
from myagent.protocol import AssistantTurn, ToolCall, ToolResult
from myagent.security.permissions import PermissionEffect, PermissionEngine, PermissionRule
from myagent.tools.base import ExecutionContext, Tool, ToolSpec
from myagent.tools.registry import ToolRegistry


class FakeTool(Tool):
    spec = ToolSpec("fake", "Fake test tool", {"type": "object", "properties": {}}, "read", True, True)

    def execute(self, call_id, arguments, context):
        return ToolResult(call_id, "fake result")


class FakeProvider:
    def __init__(self):
        self.calls = 0
        self.results = []

    def respond(self, system_prompt, messages, tool_definitions):
        self.calls += 1
        if self.calls == 1:
            return AssistantTurn(tool_calls=(ToolCall("call-1", "fake", {}),))
        return AssistantTurn("completed")

    def append_tool_results(self, results):
        self.results.extend(results)


def test_agent_core_is_provider_independent(tmp_path: Path) -> None:
    registry = ToolRegistry()
    registry.register(FakeTool())
    permissions = PermissionEngine([PermissionRule("read", "*", PermissionEffect.ALLOW)])
    context = ExecutionContext(tmp_path, permissions)
    provider = FakeProvider()
    response = Agent(provider, registry, permissions, context).run("do it")
    assert response.text == "completed"
    assert provider.results[0].content == "fake result"
