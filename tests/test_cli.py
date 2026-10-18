import json
from unittest.mock import MagicMock, patch

from myagent.cli.repl import main
from myagent.config import AgentConfig, ModelProfile
from myagent.protocol import AgentResponse


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
