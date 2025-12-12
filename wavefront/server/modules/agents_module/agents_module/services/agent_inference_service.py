import time
from typing import Any, Dict, List, Optional
from uuid import UUID

from agents_module.services.agent_crud_service import AgentCrudService
from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.models.llm_inference_config import LlmInferenceConfig
from flo_ai import AgentBuilder, Agent, BaseMessage, FloUtils
from flo_ai.llm import OpenAI, Anthropic, Gemini, OllamaLLM, OpenAIVLLM
from common_module.log.logger import logger
from tools_module.registry.tool_loader import ToolLoader
import yaml


class AgentInferenceService:
    """Service for handling agent inference operations"""

    def __init__(
        self,
        cache_manager: CacheManager,
        tool_loader: ToolLoader,
        agent_crud_service: AgentCrudService,
    ):
        """
        Initialize the agent inference service

        Args:
            cache_manager: Cache manager instance
            tool_loader: Tool loader instance
            agent_crud_service: Agent CRUD service for fetching agent YAML
        """
        self.cache_manager = cache_manager
        self.tool_loader = tool_loader
        self.agent_crud_service = agent_crud_service

    async def create_agent_from_yaml(
        self,
        yaml_content: str,
        agent_name: str,
        llm_config: Optional[LlmInferenceConfig] = None,
        access_token: Optional[str] = None,
        app_key: Optional[str] = None,
    ):
        """
        Create agent instance from YAML configuration

        Args:
            yaml_content: YAML configuration content
            agent_name: The name of the agent for logging purposes
            llm_config: Optional LLM configuration to override agent's default LLM

        Returns:
            Agent instance created from YAML
        """
        logger.info(f'Creating agent from YAML for agent: {agent_name}')

        # Add tools if provided in the yaml file
        yaml_data = yaml.safe_load(yaml_content)
        tool_names = yaml_data.get('agent', {}).get('tools', [])
        tool_register = {}
        if tool_names:
            logger.info(f'Loading tools for agent {agent_name}: {tool_names}')
            for tool in tool_names:
                tools = self.tool_loader.load_tool_with_name(tool.get('name'))
                tool_register[tool.get('name')] = tools
        else:
            logger.warning(f'No tools were loaded for agent {agent_name}')

        agent_builder = AgentBuilder.from_yaml(
            yaml_str=yaml_content,
            tool_registry=tool_register,
            access_token=access_token,
            app_key=app_key,
        )

        # Override LLM if config is provided
        if llm_config:
            logger.info(
                f'Overriding LLM with config: {llm_config.display_name} (type: {llm_config.type})'
            )
            llm_instance = self._create_llm_instance(llm_config)
            agent_builder = agent_builder.with_llm(llm_instance)

        agent = agent_builder.build()
        logger.info(f'Successfully created agent for agent: {agent_name}')
        return agent

    def _create_llm_instance(self, config: LlmInferenceConfig):
        """
        Create LLM instance based on configuration

        Args:
            config: LLM inference configuration

        Returns:
            LLM instance
        """
        if config.type == 'openai':
            return OpenAI(model=config.llm_model, api_key=config.api_key)
        elif config.type == 'azure_openai':
            return OpenAI(
                model=config.llm_model, api_key=config.api_key, base_url=config.base_url
            )
        elif config.type == 'anthropic':
            return Anthropic(model=config.llm_model, api_key=config.api_key)
        elif config.type == 'gemini':
            return Gemini(model=config.llm_model, api_key=config.api_key)
        elif config.type == 'ollama':
            return OllamaLLM(model=config.llm_model, base_url=config.base_url)
        elif config.type == 'vllm':
            return OpenAIVLLM(model=config.llm_model, base_url=config.base_url)
        else:
            raise ValueError(f'Unsupported LLM type: {config.type}')

    async def run_agent_inference(
        self,
        agent: Agent,
        inputs: List[BaseMessage] | str,
        variables: Dict[str, Any],
        agent_name: str,
        output_json_enabled: bool = True,
    ) -> tuple[str, float]:
        """
        Run agent inference with provided variables

        Args:
            agent: Agent instance
            inputs: Inputs to use for inference
            variables: Variables to pass to the agent
            agent_name: The name of the agent for logging purposes
            output_json_enabled: Whether to extract JSON from the response

        Returns:
            tuple: (result, execution_time)
        """
        logger.info(
            f'Running inference for agent {agent_name} with variables: {list(variables.keys())}'
        )
        start_time = time.time()

        # Use a generic prompt that allows the agent to use the variables
        result_str = await agent.run(inputs, variables=variables)

        # Conditionally extract JSON based on output_json_enabled flag
        if output_json_enabled:
            result = FloUtils.extract_jsons_from_string(result_str)
        else:
            result = result_str

        execution_time = time.time() - start_time
        logger.info(
            f'Successfully completed inference for agent {agent_name} in {execution_time:.2f} seconds'
        )

        return result, execution_time

    async def perform_inference(
        self,
        agent_id: str,
        namespace: str,
        variables: Dict[str, Any],
        inputs: List[BaseMessage] | str,
        llm_config: Optional[LlmInferenceConfig] = None,
        output_json_enabled: bool = True,
        access_token: Optional[str] = None,
        app_key: Optional[str] = None,
    ) -> tuple[str, float]:
        """
        Complete inference workflow: fetch YAML, create agent, run inference

        Args:
            agent_id: The ID of the agent
            namespace: The namespace of the agent
            variables: Variables to pass to the agent
            inputs: Inputs to use for inference
            llm_config: Optional LLM configuration to override agent's default LLM
            output_json_enabled: Whether to extract JSON from the response

        Returns:
            tuple: (result, execution_time)
        """

        # Fetch agent YAML using CRUD service
        yaml_content = await self.agent_crud_service.get_agent_yaml_from_bucket(
            agent_id, namespace
        )

        # Create agent from YAML with optional LLM override and tools
        agent = await self.create_agent_from_yaml(
            yaml_content, agent_id, llm_config, access_token, app_key
        )

        # Run inference
        result, execution_time = await self.run_agent_inference(
            agent, inputs, variables, agent_id, output_json_enabled
        )

        return result, execution_time

    async def perform_inference_v2(
        self,
        agent_id: UUID,
        variables: Dict[str, Any],
        inputs: List[BaseMessage] | str,
        llm_config: Optional[LlmInferenceConfig] = None,
        output_json_enabled: bool = True,
        access_token: Optional[str] = None,
        app_key: Optional[str] = None,
    ) -> tuple[str, float, str]:
        """
        Complete inference workflow (v2): fetch agent from DB + cloud storage, run inference

        Args:
            agent_id: The UUID of the agent
            variables: Variables to pass to the agent
            inputs: Inputs to use for inference
            llm_config: Optional LLM configuration to override agent's default LLM
            output_json_enabled: Whether to extract JSON from the response

        Returns:
            tuple: (result, execution_time, namespace)

        Raises:
            ValueError: If agent_crud_service is not initialized or agent not found
        """
        if not self.agent_crud_service:
            raise ValueError(
                'agent_crud_service not initialized. Required for v2 inference.'
            )

        logger.info(f'Starting v2 inference for agent_id: {agent_id}')

        # Fetch agent from DB + cloud storage (includes YAML content)
        agent_data = await self.agent_crud_service.get_agent(agent_id)

        # Extract details
        namespace = agent_data['namespace']
        name = agent_data['name']
        yaml_content = agent_data['yaml_content']

        logger.info(
            f'Retrieved agent - namespace: {namespace}, name: {name}, agent_id: {agent_id}'
        )

        # Create agent from YAML with optional LLM override and tools
        agent = await self.create_agent_from_yaml(
            yaml_content, name, llm_config, access_token, app_key
        )

        # Run inference
        result, execution_time = await self.run_agent_inference(
            agent, inputs, variables, name, output_json_enabled
        )

        return result, execution_time, namespace
