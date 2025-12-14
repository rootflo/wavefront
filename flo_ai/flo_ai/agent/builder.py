from typing import List, Optional, Dict, Any, Union, Type
from flo_ai.models import AssistantMessage
import yaml
from flo_ai.agent import Agent
from flo_ai.agent.base_agent import ReasoningPattern
from flo_ai.llm import BaseLLM
from flo_ai.tool.base_tool import Tool
from flo_ai.tool.tool_config import ToolConfig, create_tool_config
from flo_ai.formatter.yaml_format_parser import FloYamlParser
from flo_ai.models.agent import AgentYamlModel, LLMConfigModel
from flo_ai.helpers.yaml_validation import format_validation_error_path
from pydantic import BaseModel, ValidationError


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
                   - 'prefilled_params': Optional dict of pre-filled parameters
                   - 'name_override': Optional custom name
                   - 'description_override': Optional custom description

        Examples:
            # Regular tools
            builder.with_tools([tool1, tool2])

            # Tool configurations
            builder.with_tools([
                ToolConfig(tool1, prefilled_params={"param1": "value1"}),
                ToolConfig(tool2, prefilled_params={"param2": "value2"})
            ])

            # Tool dictionaries
            builder.with_tools([
                {"tool": tool1, "prefilled_params": {"param1": "value1"}},
                {"tool": tool2, "prefilled_params": {"param2": "value2"}}
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
                prefilled_params = tool_item.get('prefilled_params', {})
                name_override = tool_item.get('name_override')
                description_override = tool_item.get('description_override')

                tool_config = ToolConfig(
                    tool=tool,
                    prefilled_params=prefilled_params,
                    name_override=name_override,
                    description_override=description_override,
                )
                processed_tools.append(tool_config.to_tool())
            else:
                raise ValueError(f'Unsupported tool type: {type(tool_item)}')

        self._tools = processed_tools
        return self

    def add_tool(self, tool: Tool, **prefilled_params) -> 'AgentBuilder':
        """
        Add a single tool with optional pre-filled parameters.

        Args:
            tool: The tool to add
            **prefilled_params: Pre-filled parameters for the tool

        Example:
            builder.add_tool(
                bigquery_tool,
                datasource_id="ds_123",
                project_id="my-project"
            )
        """
        if prefilled_params:
            tool_config = create_tool_config(tool, **prefilled_params)
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

    @staticmethod
    def _validate_yaml_config(config: Dict[str, Any]) -> AgentYamlModel:
        """Validate YAML configuration using Pydantic models.

        Args:
            config: Dictionary containing YAML configuration

        Returns:
            AgentYamlModel: Validated configuration model

        Raises:
            ValueError: If validation fails with formatted error messages
        """
        try:
            validated_config = AgentYamlModel(**config)
        except ValidationError as e:
            # Format validation errors for better readability
            error_messages = []
            for error in e.errors():
                field_path = format_validation_error_path(error['loc'], config)
                error_msg = f"{field_path}: {error['msg']}"
                if 'ctx' in error:
                    error_msg += f" (context: {error['ctx']})"
                error_messages.append(error_msg)
            raise ValueError(
                'YAML validation failed:\n'
                + '\n'.join(f'  - {msg}' for msg in error_messages)
            ) from e
        return validated_config

    @classmethod
    def from_yaml(
        cls,
        yaml_str: Optional[str] = None,
        yaml_file: Optional[str] = None,
        tools: Optional[List[Tool]] = None,
        base_llm: Optional[BaseLLM] = None,
        tool_registry: Optional[Dict[str, Tool]] = None,
        **kwargs,
    ) -> 'AgentBuilder':
        """Create an agent builder from a YAML configuration string or file

        Args:
            yaml_str: YAML string containing agent configuration
            yaml_file: Optional path to YAML file containing agent configuration
            tools: Optional list of tools to use with the agent
            base_llm: Optional base LLM to use
            tool_registry: Optional dictionary mapping tool names to Tool objects
                          Used to resolve tool references in YAML

        Returns:
            AgentBuilder: Configured agent builder instance
        """
        if yaml_str is None and yaml_file is None:
            raise ValueError('Either yaml_str or yaml_file must be provided')

        if yaml_str is not None and yaml_file is not None:
            raise ValueError('Only one of yaml_str or yaml_file should be provided')

        if yaml_str is not None:
            config = yaml.safe_load(yaml_str)
        else:
            if yaml_file is None:
                raise ValueError('yaml_file must be provided when yaml_str is empty')
            with open(yaml_file, 'r') as f:
                config = yaml.safe_load(f)

        validated_config = cls._validate_yaml_config(config)
        agent = validated_config.agent
        builder = cls()

        builder.with_name(agent.name or 'AI Assistant')
        # Handle both 'job' and 'prompt' fields (job takes precedence)
        prompt = agent.job or agent.prompt or 'You are a helpful AI assistant.'
        builder.with_prompt(prompt)
        builder.with_role(agent.role)
        builder.with_actas(agent.act_as)

        # Configure LLM based on model settings
        if agent.model is not None and base_llm is None:
            from flo_ai.helpers.llm_factory import create_llm_from_config

            # Merge base_url from agent if present and not in model_config
            model_config: LLMConfigModel = agent.model
            if agent.base_url is not None and model_config.base_url is None:
                # Create a new model instance with merged base_url using model_copy
                model_config = model_config.model_copy(
                    update={'base_url': agent.base_url}
                )

            llm = create_llm_from_config(model_config, **kwargs)
            builder.with_llm(llm)
        else:
            if base_llm is None:
                raise ValueError(
                    'Model must be specified in YAML configuration or base_llm must be provided'
                )
            builder.with_llm(base_llm)

        if agent.tools is not None:
            tools_list = []
            for tool in agent.tools:
                if isinstance(tool, str):
                    tools_list.append(tool)
                else:
                    # ToolConfigModel - convert to dict
                    tools_list.append(tool.model_dump(exclude_none=True))

            yaml_tools = cls._process_yaml_tools(tools_list, tool_registry)
            builder.with_tools(yaml_tools)
        elif tools:
            # Use provided tools
            builder.with_tools(tools)

        if agent.parser is not None:
            config = agent.parser.model_dump(exclude_none=True)
            parser = FloYamlParser.create(yaml_dict=config)
            builder.with_output_schema(parser.get_format())

        if agent.settings is not None:
            settings = agent.settings
            if settings.temperature is not None:
                builder._llm.temperature = settings.temperature
            if settings.max_retries is not None:
                builder.with_retries(settings.max_retries)
            if settings.reasoning_pattern is not None:
                builder.with_reasoning(ReasoningPattern[settings.reasoning_pattern])

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
                prefilled_params = tool_config.get('prefilled_params', {})
                name_override = tool_config.get('name_override')
                description_override = tool_config.get('description_override')

                # Create tool configuration
                tool_config_obj = ToolConfig(
                    tool=base_tool,
                    prefilled_params=prefilled_params,
                    name_override=name_override,
                    description_override=description_override,
                )

                # If there are pre-filled parameters or custom name/description, convert to tool
                if (
                    prefilled_params
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
