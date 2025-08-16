from typing import List, Optional, Dict, Any, Union, Type
import yaml
from flo_ai.models.agent import Agent
from flo_ai.models.base_agent import ReasoningPattern
from flo_ai.llm import BaseLLM, OpenAI, Anthropic, Gemini, OllamaLLM, VertexAI
from flo_ai.tool.base_tool import Tool
from flo_ai.formatter.yaml_format_parser import FloYamlParser
from pydantic import BaseModel


class AgentBuilder:
    """
    A facade class that simplifies the creation and configuration of AI agents.
    """

    def __init__(self):
        self._name = 'AI Assistant'
        self._system_prompt = 'You are a helpful AI assistant.'
        self._llm: Optional[BaseLLM] = None
        self._tools: List[Tool] = []
        self._max_retries = 3
        self._reasoning_pattern = ReasoningPattern.DIRECT
        self._output_schema: Optional[Dict[str, Any]] = None
        self._role: Optional[str] = None

    def with_name(self, name: str) -> 'AgentBuilder':
        """Set the agent's name"""
        self._name = name
        return self

    def with_prompt(self, system_prompt: str) -> 'AgentBuilder':
        """Set the system prompt"""
        self._system_prompt = system_prompt
        return self

    def with_llm(self, llm: BaseLLM) -> 'AgentBuilder':
        """Configure the LLM to use

        Args:
            llm: An instance of a BaseLLM implementation
        """
        self._llm = llm
        return self

    def with_tools(self, tools: List[Tool]) -> 'AgentBuilder':
        """Add tools to the agent"""
        self._tools = tools
        return self

    def with_reasoning(self, pattern: ReasoningPattern) -> 'AgentBuilder':
        """Set the reasoning pattern"""
        self._reasoning_pattern = pattern
        return self

    def with_retries(self, max_retries: int) -> 'AgentBuilder':
        """Set maximum number of retries"""
        self._max_retries = max_retries
        return self

    def with_output_schema(
        self, schema: Union[Dict[str, Any], Type[BaseModel]]
    ) -> 'AgentBuilder':
        """Set output schema for structured responses

        Args:
            schema: Either a JSON schema dictionary or a Pydantic model class
        """
        if isinstance(schema, type) and issubclass(schema, BaseModel):
            self._output_schema = schema.model_json_schema()
        else:
            self._output_schema = schema
        return self

    def with_role(self, role: str) -> 'AgentBuilder':
        """Set the agent's role"""
        self._role = role
        return self

    def build(self) -> Agent:
        """Build and return the configured agent"""
        if not self._llm:
            raise ValueError('LLM must be configured before building the agent')

        return Agent(
            name=self._name,
            system_prompt=self._system_prompt,
            llm=self._llm,
            tools=self._tools,
            max_retries=self._max_retries,
            reasoning_pattern=self._reasoning_pattern,
            output_schema=self._output_schema,
            role=self._role,
        )

    @classmethod
    def from_yaml(
        cls,
        yaml_str: str,
        tools: Optional[List[Tool]] = None,
        base_llm: Optional[BaseLLM] = None,
    ) -> 'AgentBuilder':
        """Create an agent builder from a YAML configuration string

        Args:
            yaml_str: YAML string containing agent configuration
            tools: Optional list of tools to use with the agent

        Returns:
            AgentBuilder: Configured agent builder instance
        """
        config = yaml.safe_load(yaml_str)

        if 'agent' not in config:
            raise ValueError('YAML must contain an "agent" section')

        agent_config = config['agent']
        builder = cls()

        # Set basic properties
        builder.with_name(agent_config.get('name', 'AI Assistant'))
        builder.with_prompt(agent_config.get('job', 'You are a helpful AI assistant.'))
        builder.with_role(agent_config.get('role'))

        # Configure LLM based on model settings
        if 'model' in agent_config and base_llm is None:
            base_url = agent_config.get('base_url', None)
            model_config: dict = agent_config['model']
            provider = model_config.get('provider', 'openai').lower()
            model_name = model_config.get('name')

            if not model_name:
                raise ValueError('Model name must be specified in YAML configuration')

            if provider == 'openai':
                builder.with_llm(OpenAI(model=model_name, base_url=base_url))
            elif provider == 'anthropic':
                builder.with_llm(Anthropic(model=model_name, base_url=base_url))
            elif provider == 'gemini':
                builder.with_llm(Gemini(model=model_name, base_url=base_url))
            elif provider == 'ollama':
                builder.with_llm(OllamaLLM(model=model_name, base_url=base_url))
            elif provider == 'vertexai':
                project = model_config.get('project')
                location = model_config.get('location', 'asia-south1')
                builder.with_llm(
                    VertexAI(
                        model=model_name,
                        project=project,
                        location=location,
                        base_url=base_url,
                    )
                )
            else:
                raise ValueError(f'Unsupported model provider: {provider}')
        else:
            if base_llm is None:
                raise ValueError(
                    'Model must be specified in YAML configuration or base_llm must be provided'
                )
            builder.with_llm(base_llm)

        # Set tools if provided
        if tools:
            builder.with_tools(tools)

        # Set parser if present
        if 'parser' in agent_config:
            parser = FloYamlParser.create(yaml_dict=config)
            builder.with_output_schema(parser.get_format())

        # Apply settings if present
        if 'settings' in agent_config:
            settings = agent_config['settings']
            if 'temperature' in settings:
                builder._llm.temperature = settings['temperature']
            if 'max_retries' in settings:
                builder.with_retries(settings['max_retries'])
            if 'reasoning_pattern' in settings:
                builder.with_reasoning(ReasoningPattern[settings['reasoning_pattern']])

        return builder
