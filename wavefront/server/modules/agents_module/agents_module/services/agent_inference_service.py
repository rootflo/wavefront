import time
from typing import Any, Dict, List, Optional
from uuid import UUID

from agents_module.services.agent_crud_service import AgentCrudService
from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.models.llm_inference_config import LlmInferenceConfig
from db_repo_module.models.message_processors import MessageProcessors
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from flo_ai import AgentBuilder, Agent, BaseMessage
from flo_ai.llm import OpenAI, Anthropic, Gemini, OllamaLLM, OpenAIVLLM
from flo_ai.tool.base_tool import Tool
from flo_cloud.cloud_storage import CloudStorageManager
from common_module.log.logger import logger
from llm_inference_config_module.services.llm_inference_config_service import (
    LlmInferenceConfigService,
)
from tools_module.registry.tool_loader import ToolLoader
from tools_module.utils.message_processor_fn import execute_message_processor_fn
from tools_module.utils.api_service_tool_loader import load_api_service_tool
from api_services_module.core.manager import ApiServicesManager
import yaml


class AgentInferenceService:
    """Service for handling agent inference operations"""

    def __init__(
        self,
        cache_manager: CacheManager,
        tool_loader: ToolLoader,
        agent_crud_service: AgentCrudService,
        message_processor_repository: SQLAlchemyRepository[MessageProcessors],
        cloud_storage_manager: CloudStorageManager,
        message_processor_bucket_name: str,
        api_services_manager: Optional[ApiServicesManager] = None,
        llm_inference_config_service: Optional[LlmInferenceConfigService] = None,
    ):
        """
        Initialize the agent inference service

        Args:
            cache_manager: Cache manager instance
            tool_loader: Tool loader instance
            agent_crud_service: Agent CRUD service for fetching agent YAML
            message_processor_repository: Repository for message processors
            cloud_storage_manager: Cloud storage manager instance
            message_processor_bucket_name: Name of the bucket containing message processor YAML files
            api_services_manager: API services manager instance (optional)
            llm_inference_config_service: LLM inference config service for resolving
                rootflo model_id references in agent YAMLs (required for v2 inference)
        """
        self.cache_manager = cache_manager
        self.tool_loader = tool_loader
        self.api_services_manager = api_services_manager
        self.agent_crud_service = agent_crud_service
        self.message_processor_repository = message_processor_repository
        self.cloud_storage_manager = cloud_storage_manager
        self.message_processor_bucket_name = message_processor_bucket_name
        self.llm_inference_config_service = llm_inference_config_service

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
                tool_name = tool.get('name')
                # First try to load from static registry
                tools = self.tool_loader.load_tool_with_name(tool_name)

                # If not found, try loading as message processor
                if tools is None:
                    tools = await self._try_load_message_processor_tool(tool_name)

                # If still not found, try loading as API service
                if tools is None:
                    tools = await self._try_load_api_service_tool(tool_name)

                if tools:
                    tool_register[tool_name] = tools
                else:
                    logger.warning(
                        f'Tool {tool_name} not found in registry or message processors'
                    )
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

    async def _try_load_message_processor_tool(self, tool_name: str) -> Optional[Tool]:
        """
        Attempt to load a message processor as a Tool object.

        Args:
            tool_name: Name of the tool (should match message processor name)

        Returns:
            Tool object if message processor found, None otherwise
        """

        try:
            # Query message processor by name
            processor = await self.message_processor_repository.find_one(name=tool_name)

            if not processor:
                return None

            # Load YAML to get input_schema
            yaml_key = f'message_processors/v1/{processor.source}'
            try:
                yaml_bytes = self.cloud_storage_manager.read_file(
                    self.message_processor_bucket_name, yaml_key
                )
                yaml_content = yaml_bytes.decode('utf-8')
                yaml_dict = yaml.safe_load(yaml_content)

                # Extract parameters from input_schema
                input_schema = yaml_dict.get('input_schema', {})
                properties = input_schema.get('properties', {})

                # Build parameters dict for Tool
                parameters = {
                    'message_processor_id': {
                        'type': 'string',
                        'description': 'UUID of the message processor',
                    }
                }

                for param_name, param_spec in properties.items():
                    parameters[param_name] = {
                        'type': param_spec.get('type', 'string'),
                        'description': param_spec.get('description', ''),
                    }

                # Create Tool object
                description = yaml_dict.get(
                    'description',
                    processor.description or 'Message processor function',
                )

                tool = Tool(
                    name=tool_name,
                    description=description,
                    function=execute_message_processor_fn,
                    parameters=parameters,
                )

                logger.info(f'Dynamically loaded message processor tool: {tool_name}')
                return tool

            except Exception as e:
                logger.warning(
                    f'Failed to load YAML for message processor {tool_name}: {str(e)}'
                )
                return None

        except Exception as e:
            logger.debug(f'Message processor {tool_name} not found: {str(e)}')
            return None

    async def _try_load_api_service_tool(self, tool_name: str) -> Optional[Tool]:
        """
        Attempt to load an API service as a Tool object.

        Args:
            tool_name: Name of the tool in format "service_id_api_id"

        Returns:
            Tool object if API service found, None otherwise
        """
        return await load_api_service_tool(tool_name, self.api_services_manager)

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
    ) -> tuple[List[BaseMessage], float]:
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
        result: List[BaseMessage] = await agent.run(inputs, variables=variables)

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
        version: Optional[int] = None,
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
            version: Specific version to run; defaults to the agent's current_version

        Returns:
            tuple: (result, execution_time)
        """

        # Fetch agent YAML using CRUD service
        yaml_content = await self.agent_crud_service.get_agent_yaml_from_bucket(
            agent_id, namespace, version=version
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

    async def _resolve_rootflo_llm_config(
        self, yaml_content: str
    ) -> Optional[LlmInferenceConfig]:
        """
        Resolve an LlmInferenceConfig from a YAML's `agent.model` block when the
        provider is `rootflo` and the `model_id` is a UUID pointing to a
        LlmInferenceConfig row.

        Returns None for any other case (no model block, or provider != rootflo)
        so that the caller can fall through to AgentBuilder.from_yaml's default
        behavior (which builds the LLM directly from the YAML model block).

        Raises:
            ValueError: when provider is rootflo but model_id is missing,
                not a valid UUID, or does not resolve to a LlmInferenceConfig row.
        """
        yaml_data = yaml.safe_load(yaml_content)
        model_config = yaml_data.get('agent', {}).get('model')
        if not model_config:
            return None

        if model_config.get('provider') != 'rootflo':
            return None

        model_id = model_config.get('model_id')
        if not model_id:
            raise ValueError(
                'rootflo provider requires "model_id" in agent.model block'
            )

        try:
            config_uuid = UUID(str(model_id))
        except (ValueError, TypeError):
            raise ValueError(f'rootflo model_id must be a valid UUID, got: {model_id}')

        if not self.llm_inference_config_service:
            raise ValueError(
                'llm_inference_config_service not initialized. '
                'Required to resolve rootflo model_id references.'
            )

        llm_config_dict = await self.llm_inference_config_service.get_config(
            config_uuid
        )
        if not llm_config_dict:
            raise ValueError(f'LLM inference configuration not found: {config_uuid}')

        return LlmInferenceConfig(**llm_config_dict)

    async def perform_inference_v2(
        self,
        agent_id: UUID,
        variables: Dict[str, Any],
        inputs: List[BaseMessage] | str,
        output_json_enabled: bool = True,
        access_token: Optional[str] = None,
        app_key: Optional[str] = None,
        llm_config: Optional[LlmInferenceConfig] = None,
        version: Optional[int] = None,
    ) -> tuple[List[BaseMessage], float, str]:
        """
        Complete inference workflow (v2): fetch agent from DB + cloud storage, run inference

        The LLM is resolved from the agent YAML itself: when the YAML's
        `agent.model.provider` is `rootflo`, the `model_id` is treated as a
        LlmInferenceConfig UUID and the corresponding LLM is built and applied
        via with_llm(). For any other provider, AgentBuilder.from_yaml builds
        the LLM directly from the YAML.

        Args:
            agent_id: The UUID of the agent
            variables: Variables to pass to the agent
            inputs: Inputs to use for inference
            output_json_enabled: Whether to extract JSON from the response
            version: Specific version to run; defaults to the agent's current_version

        Returns:
            tuple: (result, execution_time, namespace)

        Raises:
            ValueError: If agent_crud_service is not initialized, agent not found,
                or the YAML's rootflo model_id cannot be resolved.
        """
        if not self.agent_crud_service:
            raise ValueError(
                'agent_crud_service not initialized. Required for v2 inference.'
            )

        logger.info(
            f'Starting v2 inference for agent_id: {agent_id}, version: {version}'
        )

        # Fetch agent from DB + cloud storage (includes YAML content)
        agent_data = await self.agent_crud_service.get_agent(agent_id, version=version)

        # Extract details
        namespace = agent_data['namespace']
        name = agent_data['name']
        yaml_content = agent_data['yaml_content']

        logger.info(
            f'Retrieved agent - namespace: {namespace}, name: {name}, agent_id: {agent_id}'
        )

        # Use caller-supplied config or fall back to resolving from the YAML
        if llm_config is None:
            llm_config = await self._resolve_rootflo_llm_config(yaml_content)

        # Create agent from YAML with optional LLM override and tools
        agent = await self.create_agent_from_yaml(
            yaml_content, name, llm_config, access_token, app_key
        )

        # Run inference
        result, execution_time = await self.run_agent_inference(
            agent, inputs, variables, name, output_json_enabled
        )

        return result, execution_time, namespace
