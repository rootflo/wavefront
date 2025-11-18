from typing import List, Optional, Dict, Any, Union, Type
from flo_ai.models import AssistantMessage
import yaml
from flo_ai.models.agent import Agent
from flo_ai.models.base_agent import ReasoningPattern
from flo_ai.llm import BaseLLM
from flo_ai.tool.base_tool import Tool
from flo_ai.tool.tool_config import ToolConfig, create_tool_config
from flo_ai.formatter.yaml_format_parser import FloYamlParser
from pydantic import BaseModel


class AgentBuilder:
    """
    A facade class that simplifies the creation and configuration of AI agents.
    """

    def __init__(self):
        self._name = 'AI Assistant'
        self._system_prompt: str | AssistantMessage = 'You are a helpful AI assistant.'
        self._llm: Optional[BaseLLM] = None
        self._tools: List[Tool] = []
        self._max_retries = 3
        self._reasoning_pattern = ReasoningPattern.DIRECT
        self._output_schema: Optional[Dict[str, Any]] = None
        self._role: Optional[str] = None
        self._act_as: Optional[str] = (
            'assistant'  # Default to 'assistant' instead of None
        )

    def with_name(self, name: str) -> 'AgentBuilder':
        """Set the agent's name"""
        self._name = name
        return self

    def with_prompt(self, system_prompt: str | AssistantMessage) -> 'AgentBuilder':
        """Set the system prompt

        Args:
            system_prompt: Either a string prompt or a list of InputMessage objects
        """
        self._system_prompt = system_prompt
        return self

    def with_llm(self, llm: BaseLLM) -> 'AgentBuilder':
        """Configure the LLM to use

        Args:
            llm: An instance of a BaseLLM implementation
        """
        self._llm = llm
        return self

    def with_tools(
        self, tools: Union[List[Tool], List[ToolConfig], List[Dict[str, Any]]]
    ) -> 'AgentBuilder':
        """
        Add tools to the agent.

        Args:
            tools: List of tools, tool configurations, or tool dictionaries.
                   Each tool dictionary should have:
                   - 'tool': The Tool object
                   - 'pre_filled_params': Optional dict of pre-filled parameters
                   - 'name_override': Optional custom name
                   - 'description_override': Optional custom description

        Examples:
            # Regular tools
            builder.with_tools([tool1, tool2])

            # Tool configurations
            builder.with_tools([
                ToolConfig(tool1, pre_filled_params={"param1": "value1"}),
                ToolConfig(tool2, pre_filled_params={"param2": "value2"})
            ])

            # Tool dictionaries
            builder.with_tools([
                {"tool": tool1, "pre_filled_params": {"param1": "value1"}},
                {"tool": tool2, "pre_filled_params": {"param2": "value2"}}
            ])
        """
        processed_tools = []

        for tool_item in tools:
            if isinstance(tool_item, Tool):
                # Regular tool - add as is
                processed_tools.append(tool_item)
            elif isinstance(tool_item, ToolConfig):
                # Tool configuration - convert to tool
                processed_tools.append(tool_item.to_tool())
            elif isinstance(tool_item, dict):
                # Tool dictionary - convert to ToolConfig then to tool
                tool = tool_item['tool']
                pre_filled_params = tool_item.get('pre_filled_params', {})
                name_override = tool_item.get('name_override')
                description_override = tool_item.get('description_override')

                tool_config = ToolConfig(
                    tool=tool,
                    pre_filled_params=pre_filled_params,
                    name_override=name_override,
                    description_override=description_override,
                )
                processed_tools.append(tool_config.to_tool())
            else:
                raise ValueError(f'Unsupported tool type: {type(tool_item)}')

        self._tools = processed_tools
        return self

    def add_tool(self, tool: Tool, **pre_filled_params) -> 'AgentBuilder':
        """
        Add a single tool with optional pre-filled parameters.

        Args:
            tool: The tool to add
            **pre_filled_params: Pre-filled parameters for the tool

        Example:
            builder.add_tool(
                bigquery_tool,
                datasource_id="ds_123",
                project_id="my-project"
            )
        """
        if pre_filled_params:
            tool_config = create_tool_config(tool, **pre_filled_params)
            self._tools.append(tool_config.to_tool())
        else:
            self._tools.append(tool)
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

    def with_actas(self, act_as: str) -> 'AgentBuilder':
        """Set the agent's role"""
        self._act_as = act_as
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
            act_as=self._act_as,
        )

    @classmethod
    def from_yaml(
        cls,
        yaml_str: str,
        tools: Optional[List[Tool]] = None,
        base_llm: Optional[BaseLLM] = None,
        tool_registry: Optional[Dict[str, Tool]] = None,
        **kwargs,
    ) -> 'AgentBuilder':
        """Create an agent builder from a YAML configuration string

        Args:
            yaml_str: YAML string containing agent configuration
            tools: Optional list of tools to use with the agent
            base_llm: Optional base LLM to use
            tool_registry: Optional dictionary mapping tool names to Tool objects
                          Used to resolve tool references in YAML

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
        builder.with_actas(agent_config.get('act_as'))

        # Configure LLM based on model settings
        if 'model' in agent_config and base_llm is None:
            from flo_ai.helpers.llm_factory import create_llm_from_config

            model_config: dict = agent_config['model']
            # Merge base_url from agent_config if present and not in model_config
            if 'base_url' in agent_config and 'base_url' not in model_config:
                model_config = {**model_config, 'base_url': agent_config['base_url']}

            llm = create_llm_from_config(model_config, **kwargs)
            builder.with_llm(llm)
        else:
            if base_llm is None:
                raise ValueError(
                    'Model must be specified in YAML configuration or base_llm must be provided'
                )
            builder.with_llm(base_llm)

        # Handle tools configuration
        if 'tools' in agent_config:
            # Process tools from YAML configuration
            yaml_tools = cls._process_yaml_tools(agent_config['tools'], tool_registry)
            builder.with_tools(yaml_tools)
        elif tools:
            # Use provided tools
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

    @classmethod
    def _process_yaml_tools(
        cls,
        tools_config: List[Dict[str, Any]],
        tool_registry: Optional[Dict[str, Tool]] = None,
    ) -> List[Tool]:
        """Process tools configuration from YAML.

        Args:
            tools_config: List of tool configurations from YAML
            tool_registry: Optional dictionary mapping tool names to Tool objects

        Returns:
            List[Tool]: Processed tools
        """
        processed_tools = []

        for tool_config in tools_config:
            if isinstance(tool_config, str):
                # Simple string reference - look up in registry
                if tool_registry and tool_config in tool_registry:
                    processed_tools.append(tool_registry[tool_config])
                else:
                    raise ValueError(f"Tool '{tool_config}' not found in tool registry")
            elif isinstance(tool_config, dict):
                # Tool configuration dictionary
                tool_name = tool_config.get('name')
                if not tool_name:
                    raise ValueError("Tool configuration must have a 'name' field")

                # Look up tool in registry
                if tool_registry and tool_name in tool_registry:
                    base_tool = tool_registry[tool_name]
                else:
                    raise ValueError(f"Tool '{tool_name}' not found in tool registry")

                # Extract configuration
                pre_filled_params = tool_config.get('pre_filled_params', {})
                name_override = tool_config.get('name_override')
                description_override = tool_config.get('description_override')

                # Create tool configuration
                tool_config_obj = ToolConfig(
                    tool=base_tool,
                    pre_filled_params=pre_filled_params,
                    name_override=name_override,
                    description_override=description_override,
                )

                # If there are pre-filled parameters or custom name/description, convert to tool
                if (
                    pre_filled_params
                    or name_override is not None
                    or description_override is not None
                ):
                    processed_tools.append(tool_config_obj.to_tool())
                else:
                    # No pre-filled params and no custom name/description, use original tool
                    processed_tools.append(base_tool)
            else:
                raise ValueError(
                    f'Invalid tool configuration type: {type(tool_config)}'
                )

        return processed_tools
