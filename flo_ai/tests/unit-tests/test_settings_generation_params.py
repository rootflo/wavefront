"""
Tests for generation params declared in a YAML `settings:` block.

`settings:` accepted only temperature, max_retries and reasoning_pattern, and
because pydantic ignores unknown keys by default a `settings.max_tokens` was
swallowed without a word. The only route to a token limit was the LLM inference
config, which is per-config rather than per-agent.
"""

import pytest

from flo_ai.agent import AgentBuilder
from flo_ai.arium.builder import AriumBuilder
from flo_ai.llm import Gemini, OpenAI
from flo_ai.models.agent import SettingsModel


@pytest.fixture(autouse=True)
def openai_api_key(monkeypatch):
    """The openai SDK client refuses to construct without a key."""
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-test')


def agent_yaml(settings: str) -> str:
    """An agent YAML carrying the given settings block."""
    return f"""
apiVersion: flo/alpha-v1
metadata:
  name: translator-agent
  version: 1.0.0
agent:
  name: translator
  job: You are a translator.
  model:
    provider: openai
    name: gpt-4o-mini
  settings:
{settings}
"""


class TestSettingsModel:
    """Test cases for the fields `settings:` accepts."""

    def test_generation_params_are_accepted(self):
        """Test generation params are accepted."""
        settings = SettingsModel(
            temperature=0.2,
            max_tokens=500,
            top_p=0.9,
            top_k=40,
            frequency_penalty=0.5,
            presence_penalty=0.25,
            seed=42,
        )

        assert settings.generation_params() == {
            'max_tokens': 500,
            'top_p': 0.9,
            'top_k': 40,
            'frequency_penalty': 0.5,
            'presence_penalty': 0.25,
            'seed': 42,
        }

    def test_temperature_is_not_a_generation_param(self):
        """It is a constructor argument on the wrappers, applied separately."""
        settings = SettingsModel(temperature=0.2, max_tokens=500)

        assert settings.generation_params() == {'max_tokens': 500}

    def test_unset_params_are_absent(self):
        """An unset field must fall through to the provider's own default."""
        assert SettingsModel(temperature=0.2).generation_params() == {}

    def test_agent_settings_are_not_generation_params(self):
        """Test agent settings are not generation params."""
        settings = SettingsModel(max_retries=5, reasoning_pattern='REACT')

        assert settings.generation_params() == {}

    def test_out_of_range_values_are_rejected(self):
        """Declared fields mean a bad value fails loudly at validation."""
        with pytest.raises(ValueError):
            SettingsModel(top_p=1.5)

        with pytest.raises(ValueError):
            SettingsModel(max_tokens=0)


class TestAgentBuilderGenerationParams:
    """Test cases for with_generation_params reaching the request."""

    def test_params_reach_the_llm(self):
        """Test params reach the llm."""
        llm = OpenAI(model='gpt-4o-mini', api_key='sk-test')

        agent = (
            AgentBuilder()
            .with_llm(llm)
            .with_generation_params(top_p=0.9, seed=42)
            .build()
        )

        assert agent.llm.kwargs == {'top_p': 0.9, 'seed': 42}

    def test_nulls_are_ignored(self):
        """An unset YAML field arrives as None and must not be forwarded."""
        llm = OpenAI(model='gpt-4o-mini', api_key='sk-test')

        agent = (
            AgentBuilder()
            .with_llm(llm)
            .with_generation_params(top_p=0.9, seed=None)
            .build()
        )

        assert agent.llm.kwargs == {'top_p': 0.9}

    def test_params_survive_a_later_with_llm(self):
        """with_llm() replaces the instance, so eager application would be lost."""
        builder = AgentBuilder().with_generation_params(top_p=0.9)
        override = OpenAI(model='gpt-4o-mini', api_key='sk-test')

        agent = builder.with_llm(override).build()

        assert agent.llm.kwargs == {'top_p': 0.9}

    def test_the_token_limit_is_named_for_the_provider(self):
        """One canonical YAML key, one spelling per provider."""
        openai_agent = (
            AgentBuilder()
            .with_llm(OpenAI(model='gpt-4o-mini', api_key='sk-test'))
            .with_generation_params(max_tokens=500)
            .build()
        )
        gemini_agent = (
            AgentBuilder()
            .with_llm(Gemini(model='gemini-2.5-flash', api_key='sk-test'))
            .with_generation_params(max_tokens=500)
            .build()
        )

        assert openai_agent.llm.kwargs == {'max_completion_tokens': 500}
        assert gemini_agent.llm.kwargs == {'max_output_tokens': 500}

    def test_settings_outrank_the_constructed_llm(self):
        """The LLM comes from a config; `settings:` is the more specific source."""
        llm = OpenAI(model='gpt-4o-mini', api_key='sk-test', top_p=0.1, seed=7)

        agent = AgentBuilder().with_llm(llm).with_generation_params(top_p=0.9).build()

        assert agent.llm.kwargs == {'top_p': 0.9, 'seed': 7}


class TestAgentYamlGenerationParams:
    """Test cases for the params travelling from YAML to the request."""

    def test_settings_block_is_applied(self):
        """Test settings block is applied."""
        agent = AgentBuilder.from_yaml(
            yaml_str=agent_yaml('    max_tokens: 500\n    top_p: 0.9\n    seed: 42')
        ).build()

        assert agent.llm.kwargs == {
            'max_completion_tokens': 500,
            'top_p': 0.9,
            'seed': 42,
        }

    def test_a_settings_block_without_them_changes_nothing(self):
        """Test a settings block without them changes nothing."""
        agent = AgentBuilder.from_yaml(
            yaml_str=agent_yaml('    temperature: 0.2\n    max_retries: 2')
        ).build()

        assert agent.llm.kwargs == {}
        assert agent.llm.temperature == 0.2

    def test_arium_agents_get_the_same_treatment(self):
        """The workflow builder and the agent builder must not disagree."""
        yaml_config = """
        arium:
          agents:
            - name: A
              job: "Agent A"
              model:
                provider: openai
                name: gpt-4o-mini
              settings:
                max_tokens: 500
                top_p: 0.9
          workflow:
            start: A
            edges:
              - from: A
                to: [end]
            end: [A]
        """

        arium = AriumBuilder.from_yaml(yaml_str=yaml_config).build()

        assert arium.nodes['A'].llm.kwargs == {
            'max_completion_tokens': 500,
            'top_p': 0.9,
        }


class TestModelBlockTokenLimit:
    """`model.max_tokens` and `model.timeout` were read by nothing at all."""

    def test_model_max_tokens_reaches_the_request(self):
        """Test model max tokens reaches the request."""
        yaml_str = """
apiVersion: flo/alpha-v1
metadata:
  name: translator-agent
  version: 1.0.0
agent:
  name: translator
  job: You are a translator.
  model:
    provider: openai
    name: gpt-4o-mini
    max_tokens: 500
"""

        agent = AgentBuilder.from_yaml(yaml_str=yaml_str).build()

        assert agent.llm.kwargs == {'max_completion_tokens': 500}

    def test_model_timeout_configures_the_client(self):
        """A request timeout is a client option, not a generation param."""
        yaml_str = """
apiVersion: flo/alpha-v1
metadata:
  name: translator-agent
  version: 1.0.0
agent:
  name: translator
  job: You are a translator.
  model:
    provider: openai
    name: gpt-4o-mini
    timeout: 30
"""

        agent = AgentBuilder.from_yaml(yaml_str=yaml_str).build()

        assert agent.llm.client.timeout == 30
        assert agent.llm.kwargs == {}

    def test_settings_outrank_the_model_block(self):
        """Same precedence as temperature: the agent's settings are specific."""
        yaml_str = """
apiVersion: flo/alpha-v1
metadata:
  name: translator-agent
  version: 1.0.0
agent:
  name: translator
  job: You are a translator.
  model:
    provider: openai
    name: gpt-4o-mini
    max_tokens: 500
  settings:
    max_tokens: 100
"""

        agent = AgentBuilder.from_yaml(yaml_str=yaml_str).build()

        assert agent.llm.kwargs == {'max_completion_tokens': 100}


if __name__ == '__main__':
    pytest.main([__file__])
