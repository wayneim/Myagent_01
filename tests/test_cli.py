import json
from unittest.mock import MagicMock, patch

import pytest

from myagent.cli.repl import main
from myagent.config import AgentConfig, ModelProfile
from myagent.protocol import AgentResponse, AssistantTurn, ToolCall


def config(tmp_path):
    return AgentConfig(tmp_path, ModelProfile('minimax', 'fixture', 'http://localhost'), 'fixture-key')


def test_repl_continues_one_session_until_new_command(monkeypatch, tmp_path):
    agent = MagicMock()
    agent.new_session.side_effect = [MagicMock(session_id='first'), MagicMock(session_id='second')]
    prompts = iter(['first task', 'followup', ':new', 'fresh task', ':quit'])
    monkeypatch.setattr('sys.argv', ['myagent'])
    monkeypatch.setattr('builtins.input', lambda _: next(prompts))
    with patch('myagent.cli.repl.AgentConfig.from_environment', return_value=config(tmp_path)), patch('myagent.cli.repl.build_agent', return_value=agent):
        assert main() == 0
    assert [call.kwargs['session_id'] for call in agent.run.call_args_list] == ['first', 'first', 'second']


def test_one_shot_failure_returns_nonzero_status(monkeypatch, tmp_path):
    agent = MagicMock()
    agent.run.return_value = AgentResponse('step limit', False)
    monkeypatch.setattr('sys.argv', ['myagent', 'task'])
    with patch('myagent.cli.repl.AgentConfig.from_environment', return_value=config(tmp_path)), patch('myagent.cli.repl.build_agent', return_value=agent):
        assert main() == 1


def test_json_startup_error_is_structured(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr('sys.argv', ['myagent', '--json-events', 'task'])
    with patch('myagent.cli.repl.AgentConfig.from_environment', return_value=config(tmp_path)), patch('myagent.cli.repl.build_agent', side_effect=ValueError('Missing key')):
        assert main() == 2
    output = json.loads(capsys.readouterr().out)
    assert output == {'type': 'error', 'data': {'message': 'Missing key'}}


@pytest.mark.parametrize('json_mode,mode,stdin_tty,stderr_tty,answer,asked,allowed', [
    (True, 'auto', True, True, 'y', False, False),
    (True, 'interactive', True, True, 'yes', True, True),
    (True, 'interactive', True, True, 'n', True, False),
    (True, 'interactive', True, True, EOFError(), True, False),
    (True, 'interactive', False, True, 'y', False, False),
    (True, 'interactive', True, False, 'y', False, False),
    (True, 'deny', True, True, 'y', False, False),
    (False, 'auto', True, True, 'y', True, True),
    (False, 'auto', False, True, 'y', False, False),
    (False, 'interactive', True, True, 'y', True, True),
    (False, 'deny', True, True, 'y', False, False),
])
def test_cli_approval_modes_with_real_file_tool(
    monkeypatch, tmp_path, capsys, json_mode, mode, stdin_tty, stderr_tty, answer, asked, allowed,
):
    args = ['myagent', '--approval-mode', mode, 'write a file']
    if json_mode:
        args.append('--json-events')
    monkeypatch.setattr('sys.argv', args)
    provider = MagicMock()
    provider.respond.side_effect = [
        AssistantTurn(tool_calls=(ToolCall('write-1', 'write_file', {'path': 'result.txt', 'content': 'approved'}),)),
        AssistantTurn('finished'),
    ]
    with (
        patch('myagent.cli.repl.AgentConfig.from_environment', return_value=config(tmp_path)),
        patch('myagent.runtime.provider_registry.create', return_value=provider),
        patch('myagent.cli.repl.sys.stdin.isatty', return_value=stdin_tty),
        patch('myagent.cli.repl.sys.stderr.isatty', return_value=stderr_tty),
        patch('builtins.input') as read,
    ):
        if isinstance(answer, Exception):
            read.side_effect = answer
        else:
            read.return_value = answer
        assert main() == 0
        assert read.call_count == int(asked)
        if asked:
            read.assert_called_once_with()  # The prompt must not be printed by input() to stdout.
    output = capsys.readouterr()
    assert ('Permission required: edit result.txt' in output.err) == asked
    assert ('Allow this action? [y/N]' in output.err) == asked
    target = tmp_path / 'result.txt'
    assert target.exists() == allowed
    if allowed:
        assert target.read_text(encoding='utf-8') == 'approved'
    if json_mode:
        events = [json.loads(line) for line in output.out.splitlines()]
        result = next(event for event in events if event['type'] == 'tool_completed')
        assert result['data']['is_error'] == (not allowed)
        if not allowed:
            assert 'Permission denied' in result['data']['content']


def test_json_terminal_approval_is_one_time(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr('sys.argv', ['myagent', '--json-events', '--approval-mode', 'interactive', 'write files'])
    provider = MagicMock()
    provider.respond.side_effect = [
        AssistantTurn(tool_calls=tuple(
            ToolCall(name, 'write_file', {'path': name, 'content': name})
            for name in ('first.txt', 'second.txt')
        )),
        AssistantTurn('finished'),
    ]
    with (
        patch('myagent.cli.repl.AgentConfig.from_environment', return_value=config(tmp_path)),
        patch('myagent.runtime.provider_registry.create', return_value=provider),
        patch('myagent.cli.repl.sys.stdin.isatty', return_value=True),
        patch('myagent.cli.repl.sys.stderr.isatty', return_value=True),
        patch('builtins.input', side_effect=['y', 'n']) as read,
    ):
        assert main() == 0
        assert read.call_count == 2
    assert (tmp_path / 'first.txt').exists()
    assert not (tmp_path / 'second.txt').exists()
    output = capsys.readouterr()
    assert output.err.count('Permission required:') == 2
    results = [json.loads(line)['data'] for line in output.out.splitlines() if json.loads(line)['type'] == 'tool_completed']
    assert [result['is_error'] for result in results] == [False, True]


def test_json_default_approval_denial_still_allows_reads(monkeypatch, tmp_path, capsys):
    (tmp_path / 'source.txt').write_text('readable', encoding='utf-8')
    monkeypatch.setattr('sys.argv', ['myagent', '--json-events', 'read a file'])
    provider = MagicMock()
    provider.respond.side_effect = [
        AssistantTurn(tool_calls=(ToolCall('read-1', 'read_file', {'path': 'source.txt'}),)),
        AssistantTurn('finished'),
    ]
    with (
        patch('myagent.cli.repl.AgentConfig.from_environment', return_value=config(tmp_path)),
        patch('myagent.runtime.provider_registry.create', return_value=provider),
        patch('builtins.input', side_effect=AssertionError('Must not read input')),
    ):
        assert main() == 0
    output = capsys.readouterr()
    assert output.err == ''
    result = next(json.loads(line)['data'] for line in output.out.splitlines() if json.loads(line)['type'] == 'tool_completed')
    assert not result['is_error']
    assert 'readable' in result['content']


def test_json_still_requires_one_shot_task(monkeypatch, capsys):
    monkeypatch.setattr('sys.argv', ['myagent', '--json-events', '--approval-mode', 'interactive'])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert 'requires a one-shot task' in capsys.readouterr().err
