import asyncio
import time
from typing import Any, Dict, List, Optional, Callable
import yaml

from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.models.workflow import Workflow
from db_repo_module.models.workflow_version import WorkflowVersion
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from flo_ai import AriumBuilder, BaseMessage, FloUtils, Arium, AgentBuilder, Agent
from flo_cloud.cloud_storage import CloudStorageManager
from common_module.log.logger import logger
from agents_module.utils.workflow_utils import get_workflow_yaml_key
from agents_module.utils.cache_utils import (
    get_workflow_current_version_cache_key,
    get_workflow_yaml_cache_key,
)
from agents_module.utils.version_reference_utils import (
    parse_versioned_reference,
    resolve_entity_current_version,
)
from agents_module.utils.workflow_reference_utils import (
    extract_agent_references,
    inline_subworkflow_references,
)
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
        workflow_repository: Optional[SQLAlchemyRepository[Workflow]] = None,
        workflow_version_repository: Optional[
            SQLAlchemyRepository[WorkflowVersion]
        ] = None,
        agent_crud_service: Optional[AgentCrudService] = None,
        tool_loader: Optional[ToolLoader] = None,
    ):
        """
        Initialize the workflow inference service

        Args:
            cloud_storage_manager: Cloud storage manager instance
            cache_manager: Cache manager instance
            bucket_name: Name of the bucket containing workflow YAML files
            workflow_repository: Workflow repository, used to resolve current_version
                for name-based lookups (i.e. no explicit version given)
            workflow_version_repository: WorkflowVersion repository, used to reject
                explicitly requested versions that don't exist or are soft-deleted
            agent_crud_service: Agent CRUD service for fetching agent YAMLs
            tool_loader: Tool loader for loading agent tools
        """
        self.cloud_storage_manager = cloud_storage_manager
        self.bucket_name = bucket_name
        self.cache_manager = cache_manager
        self.workflow_repository = workflow_repository
        self.workflow_version_repository = workflow_version_repository
        self.agent_crud_service = agent_crud_service
        self.tool_loader = tool_loader
        self.current_version_cache_ttl = (
            60  # short TTL for name-based version resolution
        )

    async def _resolve_workflow_current_version(
        self, workflow_name: str, namespace: str
    ) -> int:
        """
        Resolve current_version for a workflow by name+namespace, via a short-TTL
        cache so name-based lookups (no explicit version) don't hit the DB on every call.
        """
        return await resolve_entity_current_version(
            cache_manager=self.cache_manager,
            repository=self.workflow_repository,
            namespace=namespace,
            name=workflow_name,
            cache_key=get_workflow_current_version_cache_key(namespace, workflow_name),
            ttl=self.current_version_cache_ttl,
            not_found_message=f'Workflow not found: {namespace}/{workflow_name}',
            use_to_thread=True,
        )

    async def fetch_workflow_yaml(
        self, workflow_name: str, namespace: str, version: Optional[int] = None
    ) -> str:
        """
        Fetch workflow YAML configuration from cloud storage

        Args:
            workflow_name: The name of the workflow
            namespace: The namespace of the workflow
            version: Specific version to fetch; defaults to the workflow's current_version

        Returns:
            str: YAML content as string
        """
        resolved_version = version
        if resolved_version is None:
            resolved_version = await self._resolve_workflow_current_version(
                workflow_name, namespace
            )
        elif (
            self.workflow_version_repository is not None
            and self.workflow_repository is not None
        ):
            # Explicit version: reject it if it doesn't exist or was soft-deleted,
            # so a deleted version can't be run just because its YAML still lives
            # in the bucket (delete-version is a soft delete).
            workflow = await self.workflow_repository.find_one(
                name=workflow_name, namespace=namespace
            )
            if not workflow:
                raise ValueError(f'Workflow not found: {namespace}/{workflow_name}')
            version_row = await self.workflow_version_repository.find_one(
                workflow_id=workflow.id, version=resolved_version
            )
            if not version_row or version_row.is_deleted:
                raise ValueError(
                    f'Workflow YAML not found for workflow: {namespace}/{workflow_name}, version: {resolved_version}'
                )

        yaml_key = get_workflow_yaml_key(namespace, workflow_name, resolved_version)
        cache_key = get_workflow_yaml_cache_key(
            namespace, workflow_name, resolved_version
        )

        # Try to get from cache first
        cached_result = await asyncio.to_thread(self.cache_manager.get_str, cache_key)
        if cached_result:
            logger.info(
                f'Cache hit fetching workflow YAML for namespace: {namespace}, workflow: {workflow_name}, version: {resolved_version}'
            )
            return cached_result

        logger.info(
            f'Fetching workflow YAML for namespace: {namespace}, workflow: {workflow_name}, version: {resolved_version}'
        )
        yaml_bytes: bytes = await asyncio.to_thread(
            self.cloud_storage_manager.read_file, self.bucket_name, yaml_key
        )
        yaml_content = yaml_bytes.decode('utf-8')

        await asyncio.to_thread(
            self.cache_manager.add, cache_key, yaml_content, expiry=3600
        )

        logger.info(
            f'Successfully fetched workflow YAML for namespace: {namespace}, workflow: {workflow_name}, version: {resolved_version}'
        )
        return yaml_content

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
                agent_name, version = parse_versioned_reference(parts[1])

                logger.info(
                    f'Fetching and building agent: namespace={namespace}, agent_name={agent_name}, version={version}'
                )

                # Use AgentCrudService to fetch agent YAML (handles caching automatically)
                agent_yaml_content = (
                    await self.agent_crud_service.get_agent_yaml_from_bucket(
                        agent_name, namespace, version=version
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

        # Recursively inline subworkflow references at any nesting depth, then
        # rebuild the YAML string the AriumBuilder consumes.
        yaml_data = yaml.safe_load(yaml_content) or {}
        arium_config = yaml_data.get('arium', {}) or {}
        inlined_arium = await inline_subworkflow_references(
            arium_config, self.fetch_workflow_yaml
        )
        if inlined_arium is not arium_config:
            yaml_data['arium'] = inlined_arium
            yaml_content = yaml.dump(
                yaml_data, default_flow_style=False, sort_keys=False
            )

        # Extract and build referenced agents (at any nesting depth)
        agent_references = extract_agent_references(inlined_arium)
        agents_dict = {}

        if agent_references:
            logger.info(
                f'Building {len(agent_references)} referenced agents for workflow {workflow_name}'
            )
            agents_dict = await self._build_referenced_agents(
                agent_references, access_token, app_key
            )

        # Build workflow with pre-built agents and inlined subworkflows
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
        version: Optional[int] = None,
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
            version: Specific version to run; defaults to the workflow's current_version

        Returns:
            tuple: (result, execution_time)
        """

        # Fetch workflow YAML
        yaml_content = await self.fetch_workflow_yaml(workflow_name, namespace, version)

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
            workflow_data: Workflow data dict, typically from workflow_crud_service.get_workflow().
                If it already contains 'yaml_content' (i.e. the caller resolved a
                specific version up front - e.g. a pipeline's pinned
                workflow_version), that content is used directly rather than
                re-fetched, so inference runs exactly the version workflow_data
                was resolved to. Otherwise YAML is fetched by name+namespace,
                honoring workflow_data['version'] if present or falling back to
                current_version.
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
        version = workflow_data.get('version')

        logger.info(
            f'Starting v2 inference - namespace: {namespace}, name: {workflow_name}, workflow_id: {workflow_id}, version: {version}'
        )

        if 'yaml_content' in workflow_data:
            yaml_content = workflow_data['yaml_content']
        else:
            yaml_content = await self.fetch_workflow_yaml(
                workflow_name, namespace, version
            )

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
