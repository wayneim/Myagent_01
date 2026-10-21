"""Offline coding exercise: real file tools + local Python, with a scripted model."""

import sys

from myagent.core import Agent
from myagent.protocol import AssistantTurn, ToolCall, UserMessage
from myagent.runtime import LocalProcessBackend
from myagent.security.permissions import ApprovalHandler, PermissionEffect, PermissionEngine, PermissionRule
from myagent.tools.base import ExecutionContext
from myagent.tools.files import EditFileTool, ReadFileTool
from myagent.tools.registry import ToolRegistry
from myagent.tools.shell import ShellTool


def test_read_test_fail_edit_retry_test_pass_and_followup(tmp_path):
    (tmp_path / 'calc.py').write_text('def answer():\n    return 1\n', encoding='utf-8')
    command = f'"{sys.executable}" -B -c "from calc import answer; assert answer() == 2"'   # sys.executable获取当前正在运行的 Python 解释器的绝对路径。

    class Approvals(ApprovalHandler):
        def __init__(self):
            self.requests = []

        def approve(self, action, resource):
            self.requests.append((action, resource))
            return True

    class ScriptedProvider:
        def __init__(self):
            self.requests = []
            self.turns = iter([
                AssistantTurn(tool_calls=(ToolCall('read', 'read_file', {'path': 'calc.py'}),)),
                AssistantTurn(tool_calls=(ToolCall('failing-test', 'bash', {'command': command}),)),
                AssistantTurn(tool_calls=(ToolCall('bad-edit', 'edit_file', {'path': 'calc.py', 'old_string': 'return 999', 'new_string': 'return 2'}),)),
                AssistantTurn(tool_calls=(ToolCall('edit', 'edit_file', {'path': 'calc.py', 'old_string': 'return 1', 'new_string': 'return 2'}),)),
                AssistantTurn(tool_calls=(ToolCall('passing-test', 'bash', {'command': command}),)),
                AssistantTurn('Updated calc.py and verified answer() == 2.'),
                AssistantTurn('The function now returns 2.'),
            ])

        def respond(self, system_prompt, messages, tool_definitions):
            self.requests.append(list(messages))
            return next(self.turns)

    approvals = Approvals()
    permissions = PermissionEngine([
        PermissionRule('read', '*', PermissionEffect.ALLOW),
        PermissionRule('edit', '*', PermissionEffect.ASK),
        PermissionRule('shell', '*', PermissionEffect.ASK),
    ], approvals)
    context = ExecutionContext(tmp_path, permissions, sandbox_backend=LocalProcessBackend())
    tools = ToolRegistry()
    for tool in (ReadFileTool(), EditFileTool(), ShellTool()):
        tools.register(tool)
    provider = ScriptedProvider()
    agent = Agent(provider, tools, permissions, context)
    response = agent.run('Fix answer() so that it returns 2 and verify it.')
    assert response.completed
    results = [message.results[0] for message in agent.session_store.get(response.session_id).messages if hasattr(message, 'results')]
    assert [result.is_error for result in results] == [False, True, True, False, False]
    assert 'sandboxed=False' in results[-1].content
    assert [action for action, _ in approvals.requests] == ['shell', 'edit', 'edit', 'shell']
    assert 'return 2' in (tmp_path / 'calc.py').read_text(encoding='utf-8')
    assert agent.run('What changed?', session_id=response.session_id).completed
    assert [message.content for message in provider.requests[-1] if isinstance(message, UserMessage)] == [
        'Fix answer() so that it returns 2 and verify it.', 'What changed?',
    ]
