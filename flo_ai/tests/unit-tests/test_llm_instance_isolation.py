"""
Tests that building an agent or a router never mutates the LLM it was handed.

A base_llm is one object shared by every agent in a workflow. Applying an
agent's temperature to it in place therefore gave that temperature to all of
them, including agents that declared none - and routers, built after the agents,
overwrote whatever the agents had settled on.
"""

import copy

import pytest

from flo_ai.agent import AgentBuilder
from flo_ai.arium.builder import AriumBuilder
from flo_ai.arium.llm_router import DEFAULT_ROUTING_TEMPERATURE, SmartRouter
from flo_ai.llm import OpenAI, RootFloLLM


@pytest.fixture(autouse=True)
def openai_api_key(monkeypatch):
    """The openai SDK client refuses to construct without a key."""
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-test')


def shared_llm(**kwargs) -> OpenAI:
    """An LLM standing in for a base_llm passed to several agents."""
    return OpenAI(model='gpt-4o-mini', api_key='sk-test', temperature=0.7, **kwargs)


class TestAgentBuilderLeavesTheGivenLlmAlone:
    """Test cases for AgentBuilder.build() copying instead of mutating."""

    def test_temperature_does_not_reach_the_given_instance(self):
        """Test temperature does not reach the given instance."""
        llm = shared_llm()

        agent = AgentBuilder().with_llm(llm).with_temperature(0.2).build()

        assert agent.llm.temperature == 0.2
        assert llm.temperature == 0.7

    def test_generation_params_do_not_reach_the_given_instance(self):
        """kwargs is the params dict itself, so it has to be copied too."""
        llm = shared_llm()

        agent = AgentBuilder().with_llm(llm).with_generation_params(top_p=0.5).build()

        assert agent.llm.kwargs == {'top_p': 0.5}
        assert llm.kwargs == {}

    def test_agents_do_not_leak_into_each_other(self):
        """The failure this fixes: B ran at A's temperature, having set none."""
        llm = shared_llm()

        a = AgentBuilder().with_name('A').with_llm(llm).with_temperature(0.2).build()
        b = AgentBuilder().with_name('B').with_llm(llm).build()

        assert a.llm.temperature == 0.2
        assert b.llm.temperature == 0.7

    def test_an_unconfigured_build_shares_the_instance(self):
        """With nothing to apply there is nothing to isolate, so no copy."""
        llm = shared_llm()

        agent = AgentBuilder().with_llm(llm).build()

        assert agent.llm is llm

    def test_an_owned_llm_is_configured_in_place(self):
        """An LLM built for this agent alone has nobody else to leak to."""
        llm = shared_llm()

        agent = AgentBuilder().with_llm(llm, owned=True).with_temperature(0.2).build()

        assert agent.llm is llm
        assert llm.temperature == 0.2

    def test_a_yaml_built_llm_is_owned(self):
        """from_yaml builds it from the model block, so no copy is needed."""
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
  settings:
    temperature: 0.2
"""
        builder = AgentBuilder.from_yaml(yaml_str=yaml_str)

        agent = builder.build()

        assert agent.llm is builder._llm
        assert agent.llm.temperature == 0.2

    def test_the_sdk_client_is_shared(self):
        """A copy per agent must not mean a connection pool per agent."""
        llm = shared_llm()

        agent = AgentBuilder().with_llm(llm).with_temperature(0.2).build()

        assert agent.llm is not llm
        assert agent.llm.client is llm.client

    def test_the_builder_can_be_reused(self):
        """build() leaves its own state alone, so a second build repeats it."""
        llm = shared_llm()
        builder = AgentBuilder().with_llm(llm).with_temperature(0.2)

        first = builder.build()
        second = builder.build()

        assert first.llm.temperature == 0.2
        assert second.llm.temperature == 0.2
        assert first.llm is not second.llm


class TestAriumBuilderLeavesTheBaseLlmAlone:
    """Test cases for the same isolation through the workflow builder."""

    YAML = """
    arium:
      agents:
        - name: A
          job: "Agent A"
          settings:
            temperature: 0.2
        - name: B
          job: "Agent B"
      workflow:
        start: A
        edges:
          - from: A
            to: [B]
          - from: B
            to: [end]
        end: [B]
    """

    def test_only_the_configured_agent_gets_the_temperature(self):
        """Test only the configured agent gets the temperature."""
        base_llm = shared_llm()

        arium = AriumBuilder.from_yaml(yaml_str=self.YAML, base_llm=base_llm).build()

        assert arium.nodes['A'].llm.temperature == 0.2
        assert arium.nodes['B'].llm.temperature == 0.7
        assert base_llm.temperature == 0.7

    @staticmethod
    def routed_yaml(router_settings: str = '') -> str:
        """A workflow whose router shares the agents' base_llm.

        The router has no `model:` block, so the builder hands it the base_llm -
        the same object the agents hold. Routers are processed after the agents,
        so whatever a router writes to it lands last.
        """
        return f"""
        arium:
          agents:
            - name: A
              job: "Agent A"
              settings:
                temperature: 0.2
            - name: B
              job: "Agent B"
            - name: C
              job: "Agent C"
          routers:
            - name: pick
              type: smart
{router_settings}
              routing_options:
                B: "send to B"
                C: "send to C"
          workflow:
            start: A
            edges:
              - from: A
                to: [B, C]
                router: pick
              - from: B
                to: [end]
              - from: C
                to: [end]
            end: [B, C]
        """

    def test_a_router_does_not_take_over_the_agents_temperature(self):
        """A router with no temperature of its own must change nothing."""
        base_llm = shared_llm()

        arium = AriumBuilder.from_yaml(
            yaml_str=self.routed_yaml(), base_llm=base_llm
        ).build()

        assert arium.nodes['A'].llm.temperature == 0.2
        assert arium.nodes['B'].llm.temperature == 0.7
        assert base_llm.temperature == 0.7

    def test_an_explicit_router_temperature_does_not_leak(self):
        """The router's own setting applies to the router, and only to it."""
        base_llm = shared_llm()

        arium = AriumBuilder.from_yaml(
            yaml_str=self.routed_yaml(
                '              settings:\n                temperature: 0.0'
            ),
            base_llm=base_llm,
        ).build()

        assert arium.nodes['A'].llm.temperature == 0.2
        assert arium.nodes['B'].llm.temperature == 0.7
        assert base_llm.temperature == 0.7


class TestRouterLeavesTheGivenLlmAlone:
    """Test cases for BaseLLMRouter and a supplied LLM."""

    OPTIONS = {'researcher': 'Research tasks', 'analyst': 'Analysis tasks'}

    def test_an_explicit_routing_temperature_applies_to_a_copy(self):
        """Test an explicit routing temperature applies to a copy."""
        llm = shared_llm()

        router = SmartRouter(self.OPTIONS, llm=llm, temperature=0.0)

        assert router.llm.temperature == 0.0
        assert router.llm is not llm
        assert llm.temperature == 0.7

    def test_a_supplied_llm_keeps_its_own_temperature_by_default(self):
        """Nothing was asked for, so nothing should override the caller."""
        llm = shared_llm()

        router = SmartRouter(self.OPTIONS, llm=llm)

        assert router.llm is llm
        assert router.llm.temperature == 0.7
        assert router.temperature == DEFAULT_ROUTING_TEMPERATURE

    def test_a_router_built_llm_uses_the_routing_default(self):
        """Routing wants determinism, so an LLM built here is set low."""
        router = SmartRouter(self.OPTIONS)

        assert router.llm.temperature == DEFAULT_ROUTING_TEMPERATURE

    def test_temperature_zero_is_an_explicit_choice(self):
        """0.0 is falsy, so it must not be read as 'unset'."""
        llm = shared_llm()

        router = SmartRouter(self.OPTIONS, llm=llm, temperature=0.0)

        assert router.llm.temperature == 0.0


class TestRootFloLlmCopy:
    """The proxy holds a lazily built wrapper, which a copy must not share."""

    def _llm(self, **kwargs) -> RootFloLLM:
        """Llm."""
        return RootFloLLM(
            base_url='https://example.invalid',
            model_id='68baf67b-ff67-4bb1-a663-bcf08227d012',
            **kwargs,
        )

    def test_a_copy_resolves_its_own_wrapper(self):
        """Test a copy resolves its own wrapper."""
        llm = self._llm(temperature=0.7)
        llm._llm = shared_llm()
        llm._initialized = True

        clone = copy.copy(llm)

        assert clone._llm is None
        assert clone._initialized is False
        assert clone._init_lock is not llm._init_lock

    def test_a_copy_does_not_share_the_caller_kwargs(self):
        """Test a copy does not share the caller kwargs."""
        llm = self._llm(top_p=0.9)

        clone = copy.copy(llm)
        clone.apply_generation_params({'top_p': 0.1})

        assert clone._kwargs['top_p'] == 0.1
        assert llm._kwargs['top_p'] == 0.9

    def test_the_temperature_of_a_copy_is_independent(self):
        """Test the temperature of a copy is independent."""
        llm = self._llm(temperature=0.7)

        agent = AgentBuilder().with_llm(llm).with_temperature(0.2).build()

        assert agent.llm.temperature == 0.2
        assert llm.temperature == 0.7


if __name__ == '__main__':
    pytest.main([__file__])
