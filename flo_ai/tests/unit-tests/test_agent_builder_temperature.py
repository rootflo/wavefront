import pytest

from flo_ai.agent import AgentBuilder
from flo_ai.llm import OpenAI, RootFloLLM


YAML_WITH_TEMPERATURE = """
apiVersion: flo/alpha-v1
metadata:
  name: translator-agent
  version: 1.0.0
agent:
  name: translator
  model:
    provider: openai
    name: gpt-4o-mini
  settings:
    temperature: 0.2
  job: You are a translator.
"""

YAML_WITHOUT_TEMPERATURE = """
apiVersion: flo/alpha-v1
metadata:
  name: translator-agent
  version: 1.0.0
agent:
  name: translator
  model:
    provider: openai
    name: gpt-4o-mini
  settings:
    max_retries: 2
  job: You are a translator.
"""


@pytest.fixture(autouse=True)
def openai_api_key(monkeypatch):
    """The openai SDK client refuses to construct without a key."""
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-test')


class TestAgentBuilderTemperature:
    """Test cases for how AgentBuilder applies temperature to the LLM."""

    def test_yaml_temperature_survives_with_llm_override(self):
        """A with_llm() after from_yaml() must not drop the YAML temperature.

        with_llm() replaces the LLM instance from_yaml() built, so applying the
        YAML setting eagerly left the value on a discarded object.
        """
        builder = AgentBuilder.from_yaml(yaml_str=YAML_WITH_TEMPERATURE)
        override = OpenAI(model='gpt-4o-mini', api_key='sk-test', temperature=0.9)

        agent = builder.with_llm(override).build()

        assert agent.llm is override
        assert agent.llm.temperature == 0.2

    def test_yaml_temperature_applies_without_override(self):
        """The YAML temperature reaches the LLM from_yaml() built itself."""
        agent = AgentBuilder.from_yaml(yaml_str=YAML_WITH_TEMPERATURE).build()

        assert agent.llm.temperature == 0.2

    def test_llm_temperature_kept_when_yaml_omits_it(self):
        """Without a YAML temperature, the LLM keeps its own value."""
        builder = AgentBuilder.from_yaml(yaml_str=YAML_WITHOUT_TEMPERATURE)
        override = OpenAI(model='gpt-4o-mini', api_key='sk-test', temperature=0.9)

        agent = builder.with_llm(override).build()

        assert agent.llm.temperature == 0.9

    def test_with_temperature_applies_in_either_order(self):
        """with_temperature() is order-independent relative to with_llm()."""
        before = OpenAI(model='gpt-4o-mini', api_key='sk-test', temperature=0.9)
        agent = AgentBuilder().with_temperature(0.2).with_llm(before).build()
        assert agent.llm.temperature == 0.2

        after = OpenAI(model='gpt-4o-mini', api_key='sk-test', temperature=0.9)
        agent = AgentBuilder().with_llm(after).with_temperature(0.2).build()
        assert agent.llm.temperature == 0.2

    def test_temperature_zero_is_applied(self):
        """0 is a valid temperature, not an absent one."""
        llm = OpenAI(model='gpt-4o-mini', api_key='sk-test', temperature=0.9)
        agent = AgentBuilder().with_llm(llm).with_temperature(0).build()

        assert agent.llm.temperature == 0

    def test_build_leaves_llm_alone_when_unconfigured(self):
        """An unconfigured builder must not overwrite the LLM's temperature."""
        llm = OpenAI(model='gpt-4o-mini', api_key='sk-test', temperature=0.9)
        agent = AgentBuilder().with_llm(llm).build()

        assert agent.llm.temperature == 0.9


YAML_MODEL_BLOCK_TEMPERATURE = """
apiVersion: flo/alpha-v1
metadata:
  name: translator-agent
  version: 1.0.0
agent:
  name: translator
  model:
    provider: openai
    name: gpt-4o-mini
    temperature: 0.4
  job: You are a translator.
"""

YAML_BOTH_TEMPERATURES = """
apiVersion: flo/alpha-v1
metadata:
  name: translator-agent
  version: 1.0.0
agent:
  name: translator
  model:
    provider: openai
    name: gpt-4o-mini
    temperature: 0.4
  settings:
    temperature: 0.2
  job: You are a translator.
"""


class TestModelBlockTemperature:
    """Test cases for temperature declared in the YAML's model block."""

    def test_model_temperature_is_applied(self):
        """model.temperature is honoured even for providers whose factory drops it."""
        agent = AgentBuilder.from_yaml(yaml_str=YAML_MODEL_BLOCK_TEMPERATURE).build()

        assert agent.llm.temperature == 0.4

    def test_model_temperature_survives_with_llm_override(self):
        """Test model temperature survives with llm override."""
        builder = AgentBuilder.from_yaml(yaml_str=YAML_MODEL_BLOCK_TEMPERATURE)
        override = OpenAI(model='gpt-4o-mini', api_key='sk-test', temperature=0.9)

        agent = builder.with_llm(override).build()

        assert agent.llm.temperature == 0.4

    def test_settings_temperature_wins_over_model_block(self):
        """The agent's settings are more specific than its model block."""
        agent = AgentBuilder.from_yaml(yaml_str=YAML_BOTH_TEMPERATURES).build()

        assert agent.llm.temperature == 0.2


class TestRootFloLLMTemperature:
    """Test cases for temperature handling on the RootFlo proxy LLM."""

    def _llm(self, **kwargs) -> RootFloLLM:
        """Llm."""
        return RootFloLLM(
            base_url='https://example.invalid',
            model_id='68baf67b-ff67-4bb1-a663-bcf08227d012',
            **kwargs,
        )

    def test_constructor_temperature_is_readable(self):
        """Test constructor temperature is readable."""
        assert self._llm().temperature == 0.7
        assert self._llm(temperature=0.1).temperature == 0.1

    def test_assignment_reaches_the_lazily_built_wrapper(self):
        """The wrapper is built from the current temperature, not a stale copy.

        The proxy used to keep a private copy that the public attribute did not
        write to, so an assigned temperature never reached the request.
        """
        llm = self._llm(temperature=0.7)
        llm.temperature = 0.2

        assert llm._temperature == 0.2

    def test_assignment_propagates_to_an_existing_wrapper(self):
        """A temperature set after the first call updates the wrapper too."""
        llm = self._llm(temperature=0.7)
        llm._llm = OpenAI(model='gpt-4o-mini', api_key='sk-test', temperature=0.7)

        llm.temperature = 0.2

        assert llm._llm.temperature == 0.2

    def test_builder_temperature_reaches_the_proxy(self):
        """AgentBuilder and RootFloLLM agree on where temperature lives."""
        llm = self._llm(temperature=0.7)
        agent = AgentBuilder().with_llm(llm).with_temperature(0.2).build()

        assert agent.llm.temperature == 0.2
        assert agent.llm._temperature == 0.2
