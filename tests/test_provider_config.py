"""Offline configuration and startup checks; never load local credentials."""

import json
from dataclasses import replace
from unittest.mock import Mock, patch

import pytest

from myagent.cli.repl import main
from myagent.config import AgentConfig, ModelProfile
from myagent.providers.registry import ProviderRegistry, ProviderSpec, provider_registry
from myagent.runtime import build_agent


@pytest.fixture(autouse=True)
def isolated_environment():
    with patch.dict("os.environ", {}, clear=True), patch("myagent.config.load_dotenv"):
        yield


@pytest.mark.parametrize("key", [None, "", " \t "])
@pytest.mark.parametrize("provider,prefix", [("minimax", "MINIMAX"), ("qwen", "QWEN")])
def test_missing_key_is_rejected_before_loading_sdk(tmp_path, key, provider, prefix):
    config = AgentConfig(tmp_path, ModelProfile(provider, "fixture", "http://localhost"), key)
    with patch("myagent.providers.registry.import_module") as load:
        with pytest.raises(ValueError, match=f"{prefix}_API_KEY") as error:
            build_agent(config)
        assert "MYAGENT_PROVIDER=" in str(error.value)
        assert ".env" in str(error.value)
        load.assert_not_called()


def test_other_key_does_not_silently_switch_default_provider(tmp_path):
    with patch.dict("os.environ", {"QWEN_API_KEY": "fixture"}):
        config = AgentConfig.from_environment(tmp_path)
    assert config.model.provider == "minimax"
    with pytest.raises(ValueError, match="MINIMAX_API_KEY"):
        build_agent(config)


def test_explicit_provider_uses_its_own_defaults_and_credentials(tmp_path):
    with patch.dict("os.environ", {"MYAGENT_PROVIDER": " QWEN ", "QWEN_API_KEY": "fixture"}):
        config = AgentConfig.from_environment(tmp_path)
    assert config.api_key == "fixture"
    assert config.model.model == "qwen-plus"
    with patch("myagent.providers.qwen.QwenProvider") as factory:
        assert provider_registry.create(config) is factory.return_value
        factory.assert_called_once_with("fixture", config.model.base_url, "qwen-plus")


def test_new_registration_drives_environment_and_factory_without_runtime_changes(tmp_path):
    registry = ProviderRegistry()
    spec = ProviderSpec("fixture", "FIXTURE", "test-model", "http://localhost", "fixture.module:Provider")
    registry.register(spec)
    factory = Mock()
    module = Mock(Provider=factory)
    with patch("myagent.config.provider_registry", registry), patch.dict("os.environ", {
        "MYAGENT_PROVIDER": "fixture", "FIXTURE_API_KEY": " fixture-key ",
        "FIXTURE_MODEL": "override", "FIXTURE_BASE_URL": "http://override",
    }):
        config = AgentConfig.from_environment(tmp_path)
    with patch("myagent.providers.registry.import_module", return_value=module):
        assert registry.create(config) is factory.return_value
    factory.assert_called_once_with("fixture-key", "http://override", "override")
    with pytest.raises(ValueError, match="already registered"):
        registry.register(spec)


@pytest.mark.parametrize("field", ["model", "base_url"])
def test_empty_model_settings_rejected_before_client_creation(tmp_path, field):
    profile = replace(ModelProfile("minimax", "fixture", "http://localhost"), **{field: "  "})
    with patch("myagent.providers.registry.import_module") as load:
        with pytest.raises(ValueError, match="must not be empty"):
            build_agent(AgentConfig(tmp_path, profile, "fixture"))
        load.assert_not_called()


@pytest.mark.parametrize("json_mode", [False, True])
def test_cli_missing_configuration_has_actionable_error_and_no_model_call(tmp_path, monkeypatch, capsys, json_mode):
    args = ["myagent", "--workspace", str(tmp_path), "task"]
    if json_mode:
        args.append("--json-events")
    monkeypatch.setattr("sys.argv", args)
    with patch("myagent.providers.registry.import_module") as load:
        assert main() == 2
        load.assert_not_called()
    output = capsys.readouterr().out
    if json_mode:
        event = json.loads(output)
        assert event["type"] == "error"
        output = event["data"]["message"]
    assert "MINIMAX_API_KEY" in output
    assert "QWEN_API_KEY" in output
    assert ".env" in output
