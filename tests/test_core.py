from pathlib import Path
from copy import deepcopy

import pytest

from myagent.core import Agent
from myagent.protocol import AssistantTurn, EventType, ToolCall, ToolResult, ToolResultsMessage, UserMessage
from myagent.provider import ProviderError
from myagent.security.permissions import PermissionEffect, PermissionEngine, PermissionRule
from myagent.tools.base import ExecutionContext, Tool, ToolSpec
from myagent.tools.registry import ToolRegistry


class FakeTool(Tool):
    spec = ToolSpec("fake", "Fake test tool", {"type": "object", "properties": {}}, "read", True, True)

    def execute(self, call_id, arguments, context):
        return ToolResult(call_id, "fake result")


class FakeProvider:
    def __init__(self, turns=None):
        self.turns = iter(turns or [AssistantTurn(tool_calls=(ToolCall("call-1", "fake", {}),)), AssistantTurn("completed")])
        self.requests = []

    def respond(self, system_prompt, messages, tool_definitions):
        self.requests.append(deepcopy(messages))
        turn = next(self.turns)
        if isinstance(turn, BaseException):
            raise turn
        return turn

def make_agent(tmp_path, turns=None, tool=None, permissions=None):
    registry = ToolRegistry()
    registry.register(tool or FakeTool())
    permissions = permissions or PermissionEngine([PermissionRule("read", "*", PermissionEffect.ALLOW)])
    context = ExecutionContext(tmp_path, permissions)
    return Agent(FakeProvider(turns), registry, permissions, context)


def test_agent_core_is_provider_independent(tmp_path: Path) -> None:
    agent = make_agent(tmp_path)
    response = agent.run("do it")
    assert response.text == "completed"
    history = agent.provider.requests[-1]
    assert history[0] == UserMessage("do it")
    assert history[1].tool_calls[0].call_id == "call-1"
    assert history[2].results == (ToolResult("call-1", "fake result"),)
    assert agent.session_store.get(response.session_id).messages[-1].text == "completed"


def test_followup_includes_both_user_turns_and_new_session_is_isolated(tmp_path):
    agent = make_agent(tmp_path, [AssistantTurn("first answer"), AssistantTurn("second answer"), AssistantTurn("fresh")])
    first = agent.run("first task")
    second = agent.run("second task", session_id=first.session_id)
    assert second.session_id == first.session_id
    assert agent.provider.requests[1] == [UserMessage("first task"), AssistantTurn("first answer"), UserMessage("second task")]
    third = agent.run("new task")
    assert third.session_id != first.session_id
    assert agent.provider.requests[2] == [UserMessage("new task")]


@pytest.mark.parametrize("failure", ["denied", "unknown", "bad_arguments", "exception"])
def test_failed_tool_is_returned_to_model_and_loop_continues(tmp_path, failure):
    class BrokenTool(FakeTool):
        def execute(self, *args):
            raise RuntimeError("fixture failure")
    tool = BrokenTool() if failure == "exception" else FakeTool()
    call = ToolCall("call-error", "missing" if failure == "unknown" else "fake", [] if failure == "bad_arguments" else {})
    permissions = PermissionEngine([PermissionRule("read", "*", PermissionEffect.DENY if failure == "denied" else PermissionEffect.ALLOW)])
    agent = make_agent(tmp_path, [AssistantTurn(tool_calls=(call,)), AssistantTurn("recovered")], tool, permissions)
    response = agent.run("do it")
    assert response.completed
    result = agent.provider.requests[-1][-1].results[0]
    assert result.call_id == "call-error"
    assert result.is_error


def test_multiple_calls_get_one_result_each_even_if_one_is_unknown(tmp_path):
    calls = (ToolCall("one", "fake", {}), ToolCall("two", "missing", {}), ToolCall("three", "fake", {}))
    agent = make_agent(tmp_path, [AssistantTurn(tool_calls=calls), AssistantTurn("done")])
    agent.run("batch")
    results = agent.provider.requests[-1][-1].results
    assert [result.call_id for result in results] == ["one", "two", "three"]
    assert [result.is_error for result in results] == [False, True, False]


def test_interrupt_closes_batch_and_followup_remains_valid(tmp_path):
    class InterruptTool(FakeTool):
        calls = 0
        def execute(self, *args):
            self.calls += 1
            raise KeyboardInterrupt()
    tool = InterruptTool()
    calls = (ToolCall("one", "fake", {}), ToolCall("two", "fake", {}))
    agent = make_agent(tmp_path, [AssistantTurn(tool_calls=calls), AssistantTurn("continued")], tool)
    interrupted = agent.run("interrupt")
    session = agent.session_store.get(interrupted.session_id)
    assert not interrupted.completed
    assert tool.calls == 1
    assert [result.call_id for result in session.messages[-1].results] == ["one", "two"]
    assert session.events[-1].type == EventType.TASK_CANCELLED
    assert agent.run("continue", session_id=session.session_id).completed


def test_step_limit_keeps_tool_results_and_reports_incomplete(tmp_path):
    agent = make_agent(tmp_path)
    response = agent.run("bounded", max_steps=1)
    assert not response.completed
    assert isinstance(agent.session_store.get(response.session_id).messages[-1], ToolResultsMessage)


def test_provider_error_is_reported_and_session_can_continue(tmp_path):
    agent = make_agent(tmp_path, [ProviderError("fixture timeout"), AssistantTurn("retried")])
    response = agent.run("first")
    assert not response.completed
    assert agent.session_store.get(response.session_id).events[-1].type == EventType.ERROR
    assert agent.run("try again", session_id=response.session_id).completed


def test_invalid_session_and_step_count_are_rejected(tmp_path):
    agent = make_agent(tmp_path)
    with pytest.raises(ValueError, match="Unknown session"):
        agent.run("task", session_id="unknown")
    with pytest.raises(ValueError, match="max_steps"):
        agent.run("task", max_steps=0)
