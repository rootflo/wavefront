import time
from typing import Any, Dict, List, Optional, Callable
import yaml

from db_repo_module.cache.cache_manager import CacheManager
from flo_ai import AriumBuilder, BaseMessage, FloUtils, Arium, AgentBuilder, Agent
from flo_cloud.cloud_storage import CloudStorageManager
from common_module.log.logger import logger
from agents_module.utils.workflow_utils import get_workflow_yaml_key
from agents_module.utils.cache_utils import get_workflow_yaml_cache_key
from flo_ai.arium import AriumEventType, AriumEvent, MessageMemoryItem
from agents_module.services.agent_crud_service import AgentCrudService
from tools_module.registry.tool_loader import ToolLoader
from tools_module.registry.function_node_registry import FUNCTION_NODE_REGISTRY


class WorkflowInferenceService:
    """Service for handling workflow inference operations"""

    def __init__(
        self,
        cloud_storage_manager: CloudStorageManager,
        cache_manager: CacheManager,
        bucket_name: str,
        agent_crud_service: Optional[AgentCrudService] = None,
        tool_loader: Optional[ToolLoader] = None,
    ):
        """
        Initialize the workflow inference service

        Args:
            cloud_storage_manager: Cloud storage manager instance
            cache_manager: Cache manager instance
            bucket_name: Name of the bucket containing workflow YAML files
            agent_crud_service: Agent CRUD service for fetching agent YAMLs
            tool_loader: Tool loader for loading agent tools
        """
        self.cloud_storage_manager = cloud_storage_manager
        self.bucket_name = bucket_name
        self.cache_manager = cache_manager
        self.agent_crud_service = agent_crud_service
        self.tool_loader = tool_loader

    async def fetch_workflow_yaml(self, workflow_name: str, namespace: str) -> str:
        """
        Fetch workflow YAML configuration from cloud storage

        Args:
            workflow_name: The name of the workflow
            namespace: The namespace of the workflow

        Returns:
            str: YAML content as string
        """
        yaml_key = get_workflow_yaml_key(namespace, workflow_name)
        cache_key = get_workflow_yaml_cache_key(namespace, workflow_name)

        # Try to get from cache first
        cached_result = self.cache_manager.get_str(cache_key)
        if cached_result:
            logger.info(
                f'Cache hit fetching workflow YAML for namespace: {namespace}, workflow: {workflow_name}'
            )
            return cached_result

        logger.info(
            f'Fetching workflow YAML for namespace: {namespace}, workflow: {workflow_name}'
        )
        yaml_bytes: bytes = self.cloud_storage_manager.read_file(
            self.bucket_name, yaml_key
        )
        yaml_content = yaml_bytes.decode('utf-8')

        self.cache_manager.add(cache_key, yaml_content, expiry=3600)

        logger.info(
            f'Successfully fetched workflow YAML for namespace: {namespace}, workflow: {workflow_name}'
        )
        return yaml_content

    def _extract_agent_references(self, yaml_content: str) -> List[str]:
        """
        Extract agent references (namespace/agent_name) from workflow YAML

        Args:
            yaml_content: YAML configuration content

        Returns:
            List of agent references in format 'namespace/agent_name'
        """
        try:
            yaml_data = yaml.safe_load(yaml_content)
            arium_config = yaml_data.get('arium', {})
            agents_config = arium_config.get('agents', [])

            agent_references = []
            for agent_def in agents_config:
                agent_name = agent_def.get('name', '')
                # If agent name contains '/', it's a reference to cloud storage
                if '/' in agent_name:
                    agent_references.append(agent_name)
                    logger.info(f'Found agent reference: {agent_name}')

            return agent_references
        except Exception as e:
            logger.error(f'Error extracting agent references from YAML: {str(e)}')
            return []

    async def _build_referenced_agents(
        self,
        agent_references: List[str],
        access_token: Optional[str] = None,
        app_key: Optional[str] = None,
    ) -> Dict[str, Agent]:
        """
        Fetch and build agent instances for referenced agents

        Args:
            agent_references: List of agent references in format 'namespace/agent_name'

        Returns:
            Dictionary mapping agent reference to built Agent instance
        """
        agents_dict = {}

        for agent_ref in agent_references:
            try:
                # Split namespace/agent_name
                if '/' not in agent_ref:
                    logger.warning(
                        f'Invalid agent reference format: {agent_ref}, expected namespace/agent_name'
                    )
                    continue

                parts = agent_ref.split('/', 1)
                namespace = parts[0]
                agent_name = parts[1]

                logger.info(
                    f'Fetching and building agent: namespace={namespace}, agent_name={agent_name}'
                )

                # Use AgentCrudService to fetch agent YAML (handles caching automatically)
                agent_yaml_content = (
                    await self.agent_crud_service.get_agent_yaml_from_bucket(
                        agent_name, namespace
                    )
                )

                # Parse YAML to get tools
                yaml_data = yaml.safe_load(agent_yaml_content)
                tool_names = yaml_data.get('agent', {}).get('tools', [])
                tool_registry = {}

                if tool_names:
                    logger.info(f'Loading tools for agent {agent_ref}: {tool_names}')
                    for tool in tool_names:
                        tool_name = tool.get('name')
                        if tool_name:
                            tools = self.tool_loader.load_tool_with_name(tool_name)
                            tool_registry[tool_name] = tools
                else:
                    logger.info(f'No tools configured for agent {agent_ref}')

                # Build agent
                agent = AgentBuilder.from_yaml(
                    yaml_str=agent_yaml_content,
                    tool_registry=tool_registry,
                    access_token=access_token,
                    app_key=app_key,
                ).build()

                agents_dict[agent_ref] = agent
                logger.info(f'Successfully built agent: {agent_ref}')

            except Exception as e:
                logger.error(f'Error building referenced agent {agent_ref}: {str(e)}')
                raise ValueError(
                    f'Failed to build referenced agent {agent_ref}: {str(e)}'
                )

        return agents_dict

    async def create_workflow_from_yaml(
        self,
        yaml_content: str,
        workflow_name: str,
        access_token: Optional[str] = None,
        app_key: Optional[str] = None,
    ):
        """
        Create workflow instance from YAML configuration

        Args:
            yaml_content: YAML configuration content
            workflow_name: The name of the workflow for logging purposes

        Returns:
            Workflow instance created from YAML
        """
        logger.info(f'Creating workflow from YAML for workflow: {workflow_name}')

        # Extract and build referenced agents
        agent_references = self._extract_agent_references(yaml_content)
        agents_dict = {}

        if agent_references:
            logger.info(
                f'Building {len(agent_references)} referenced agents for workflow {workflow_name}'
            )
            agents_dict = await self._build_referenced_agents(
                agent_references, access_token, app_key
            )

        # Build workflow with pre-built agents
        workflow_builder = AriumBuilder.from_yaml(
            agents=agents_dict,
            yaml_str=yaml_content,
            function_registry=FUNCTION_NODE_REGISTRY,
            access_token=access_token,
            app_key=app_key,
        )
        workflow = workflow_builder.build()

        logger.info(f'Successfully created workflow for workflow: {workflow_name}')
        return workflow

    async def run_workflow_inference(
        self,
        workflow: Arium,
        inputs: List[BaseMessage] | str,
        variables: Dict[str, Any],
        workflow_name: str,
        output_json_enabled: bool = True,
        event_callback: Optional[Callable[[AriumEvent], None]] = None,
        events_filter: Optional[List[AriumEventType]] = None,
    ) -> tuple[str, float]:
        """
        Run workflow inference with provided variables

        Args:
            workflow: Workflow instance
            inputs: Inputs to use for inference
            variables: Variables to pass to the workflow
            workflow_name: The name of the workflow for logging purposes
            output_json_enabled: Whether to extract JSON from the response
            event_callback: Optional callback function for workflow events
            events_filter: Optional list of event types to filter

        Returns:
            tuple: (result, execution_time)
        """
        logger.info(
            f'Running inference for workflow {workflow_name} with variables: {list(variables.keys())}'
        )
        start_time = time.time()

        # Convert string input to list if necessary
        if isinstance(inputs, str):
            processed_inputs = [inputs]
        else:
            processed_inputs = inputs

        # Run workflow inference with optional event streaming
        result_list: List[MessageMemoryItem] = await workflow.run(
            processed_inputs,
            variables=variables,
            event_callback=event_callback,
            events_filter=events_filter,
        )

        result_str = str(result_list[-1].result.content)

        # Conditionally extract JSON based on output_json_enabled flag
        if output_json_enabled:
            result = FloUtils.extract_jsons_from_string(result_str)
        else:
            result = result_str

        execution_time = time.time() - start_time
        logger.info(
            f'Successfully completed inference for workflow {workflow_name} in {execution_time:.2f} seconds'
        )

        return result, execution_time

    async def perform_inference(
        self,
        workflow_name: str,
        namespace: str,
        variables: Dict[str, Any],
        inputs: List[BaseMessage] | str,
        output_json_enabled: bool = True,
        event_callback: Optional[Callable[[AriumEvent], None]] = None,
        events_filter: Optional[List[AriumEventType]] = None,
        access_token: Optional[str] = None,
        app_key: Optional[str] = None,
    ) -> tuple[str, float]:
        """
        Complete inference workflow: fetch YAML, create workflow, run inference

        Args:
            workflow_name: The ID of the workflow
            namespace: The namespace of the workflow
            variables: Variables to pass to the workflow
            inputs: Inputs to use for inference
            output_json_enabled: Whether to extract JSON from the response
            event_callback: Optional callback function for workflow events
            events_filter: Optional list of event types to filter

        Returns:
            tuple: (result, execution_time)
        """

        # Fetch workflow YAML
        yaml_content = await self.fetch_workflow_yaml(workflow_name, namespace)

        # Create workflow from YAML
        workflow = await self.create_workflow_from_yaml(
            yaml_content, workflow_name, access_token, app_key
        )

        # Run inference with optional event streaming
        result, execution_time = await self.run_workflow_inference(
            workflow,
            inputs,
            variables,
            workflow_name,
            output_json_enabled,
            event_callback,
            events_filter,
        )

        return result, execution_time

    async def perform_inference_v2(
        self,
        workflow_data: dict,
        variables: Dict[str, Any],
        inputs: List[BaseMessage] | str,
        output_json_enabled: bool = True,
        event_callback: Optional[Callable[[AriumEvent], None]] = None,
        events_filter: Optional[List[AriumEventType]] = None,
        access_token: Optional[str] = None,
        app_key: Optional[str] = None,
    ) -> tuple[str, float]:
        """
        Complete inference workflow (v2): use pre-fetched workflow data, run inference

        Args:
            workflow_data: Pre-fetched workflow data dict from workflow_crud_service.get_workflow()
            variables: Variables to pass to the workflow
            inputs: Inputs to use for inference
            output_json_enabled: Whether to extract JSON from the response
            event_callback: Optional callback function for workflow events
            events_filter: Optional list of event types to filter

        Returns:
            tuple: (result, execution_time)
        """
        # Extract details from pre-fetched workflow data
        namespace = workflow_data['namespace']
        workflow_name = workflow_data['name']
        workflow_id = workflow_data['id']

        logger.info(
            f'Starting v2 inference - namespace: {namespace}, name: {workflow_name}, workflow_id: {workflow_id}'
        )

        yaml_content = await self.fetch_workflow_yaml(workflow_name, namespace)

        # Create workflow from YAML
        workflow = await self.create_workflow_from_yaml(
            yaml_content, workflow_name, access_token, app_key
        )

        # Run inference with optional event streaming
        result, execution_time = await self.run_workflow_inference(
            workflow,
            inputs,
            variables,
            workflow_name,
            output_json_enabled,
            event_callback,
            events_filter,
        )

        return result, execution_time
