from unittest.mock import Mock
from flo_ai.agent.builder import AgentBuilder
from flo_ai.llm.base_llm import BaseLLM
from flo_ai.llm.guarded_llm import GuardedLLM
from typing import Any, Dict, List, Optional, AsyncIterator


class DummyLLM(BaseLLM):
    def __init__(self, temperature: float = 0.7):
        super().__init__(model='dummy', temperature=temperature)

    def get_message_content(self, response: Any) -> str:
        return ''

    def format_tool_for_llm(self, tool: Any) -> Dict[str, Any]:
        return {}

    def format_tools_for_llm(self, tools: Any) -> List[Dict[str, Any]]:
        return []

    def format_image_in_message(self, image: Any) -> Any:
        return None

    async def format_document_in_message(self, document: Any) -> Any:
        return None

    async def generate(
        self,
        messages: List[Dict[str, Any]],
        functions: Optional[List[Dict[str, Any]]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {}

    async def stream(
        self,
        messages: List[Dict[str, str]],
        functions: Optional[List[Dict[str, Any]]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> AsyncIterator[Dict[str, Any]]:
        yield {}


def dummy_decorator(llm: BaseLLM, node_name: str) -> BaseLLM:
    # A simplified version of guarded_llm for testing
    return GuardedLLM(llm, engine=Mock(), principal=Mock())


def test_settings_ordering_and_copy_guard():
    base_llm = DummyLLM(temperature=0.1)

    # Build agent 1 with temperature 0.5
    agent1 = (
        AgentBuilder()
        .with_name('Agent 1')
        .with_llm(base_llm, owned=False)
        .with_temperature(0.5)
        .with_guardrail_provider(dummy_decorator)
        .build()
    )

    # Build agent 2 with temperature 0.9
    agent2 = (
        AgentBuilder()
        .with_name('Agent 2')
        .with_llm(base_llm, owned=False)
        .with_temperature(0.9)
        .with_guardrail_provider(dummy_decorator)
        .build()
    )

    # The base LLM should be untouched
    assert base_llm.temperature == 0.1

    # Each agent should have its own decorated LLM with its own temperature
    assert isinstance(agent1.llm, GuardedLLM)
    assert agent1.llm.temperature == 0.5

    assert isinstance(agent2.llm, GuardedLLM)
    assert agent2.llm.temperature == 0.9

    # The inner LLMs should be distinct copies
    assert agent1.llm._inner_llm is not agent2.llm._inner_llm
    assert agent1.llm._inner_llm is not base_llm


def test_declare_retract_support():
    base_llm = DummyLLM()
    guarded = dummy_decorator(base_llm, 'test')

    assert not guarded._supports_retract
    assert not base_llm._supports_retract

    guarded.declare_retract_support()

    # The flag should be set on the wrapper, not the inner LLM
    assert guarded._supports_retract
    assert not base_llm._supports_retract
