"""Temperature resolution: chatbot override, else the LLM config's own setting.

The zero cases are the point of this file. `temperature: 0` is a legitimate and
commonly-used setting and it is falsy, so any implementation written as
`config.get('temperature') or fallback` silently discards it and the model runs
at its default instead. That bug is invisible in the response.

Resolution spans two places -- `resolve_temperature` reads the chatbot override,
and `build_llm` lets the config's `parameters` through -- so the outcomes are
asserted on the built client, not just on the helper.
"""

from db_repo_module.models.llm_inference_config import LlmInferenceConfig

from chatbots_module.utils.llm_factory import build_llm, resolve_temperature


def _config(**overrides) -> LlmInferenceConfig:
    values = dict(
        llm_model='gpt-4o',
        display_name='test',
        api_key='test-key',
        type='openai',
        base_url=None,
        parameters=None,
    )
    values.update(overrides)
    return LlmInferenceConfig(**values)


class TestResolveTemperature:
    """Only the chatbot is consulted; the config's value is not read here."""

    def test_override_is_returned(self):
        assert resolve_temperature({'temperature': 0.3}) == 0.3

    def test_zero_override_is_honoured(self):
        # The whole reason this helper tests key presence.
        assert resolve_temperature({'temperature': 0}) == 0
        assert resolve_temperature({'temperature': 0.0}) == 0.0

    def test_absent_override_returns_none(self):
        assert resolve_temperature(None) is None
        assert resolve_temperature({}) is None
        assert resolve_temperature({'other': 1}) is None


class TestBuiltTemperature:
    """End-to-end: what the provider client actually ends up with."""

    def test_chatbot_override_beats_the_config(self):
        llm = build_llm(_config(parameters={'temperature': 0.9}), 0.2)
        assert llm.temperature == 0.2

    def test_chatbot_zero_beats_a_nonzero_config(self):
        # The regression this file exists for: 0 must not lose to 0.9.
        llm = build_llm(_config(parameters={'temperature': 0.9}), 0)
        assert llm.temperature == 0

    def test_config_temperature_applies_without_an_override(self):
        llm = build_llm(_config(parameters={'temperature': 0.9}), None)
        assert llm.temperature == 0.9

    def test_config_zero_applies_without_an_override(self):
        llm = build_llm(_config(parameters={'temperature': 0}), None)
        assert llm.temperature == 0

    def test_neither_set_leaves_the_provider_default(self):
        # flo_ai's BaseLLM default; nothing of ours should override it.
        llm = build_llm(_config(), None)
        assert llm.temperature == 0.7
