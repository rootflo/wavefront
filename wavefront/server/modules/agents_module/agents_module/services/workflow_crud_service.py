import json
import yaml
from typing import Dict, List, Optional
from uuid import UUID

from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.models.workflow import Workflow
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from flo_cloud.cloud_storage import CloudStorageManager
from flo_cloud.exceptions import CloudStorageFileNotFoundError
from common_module.log.logger import logger
from agents_module.services.namespace_service import NamespaceService
from agents_module.utils.workflow_utils import get_workflow_yaml_key
from agents_module.utils.cache_utils import (
    get_workflow_by_id_cache_key,
    get_workflow_yaml_cache_key,
    get_workflows_list_cache_key,
)
from agents_module.utils.validation_utils import validate_agent_workflow_name
from flo_ai import AriumBuilder, AgentBuilder, Agent
from agents_module.services.agent_crud_service import AgentCrudService
from tools_module.registry.tool_loader import ToolLoader
from tools_module.registry.function_node_registry import FUNCTION_NODE_REGISTRY


class WorkflowCrudService:
    """Service for handling workflow CRUD operations with DB + cloud storage"""

    def __init__(
        self,
        workflow_repository: SQLAlchemyRepository[Workflow],
        namespace_service: NamespaceService,
        cloud_storage_manager: CloudStorageManager,
        cache_manager: CacheManager,
        bucket_name: str,
        agent_crud_service: AgentCrudService,
        tool_loader: ToolLoader,
    ):
        """
        Initialize the workflow CRUD service

        Args:
            workflow_repository: Workflow repository for DB operations
            namespace_service: Namespace service for namespace operations
            cloud_storage_manager: Cloud storage manager instance
            cache_manager: Cache manager instance
            bucket_name: Name of the bucket containing workflow YAML files
            agent_crud_service: Agent CRUD service for fetching agent YAMLs
            tool_loader: Tool loader for loading agent tools
        """
        self.workflow_repository = workflow_repository
        self.namespace_service = namespace_service
        self.cloud_storage_manager = cloud_storage_manager
        self.cache_manager = cache_manager
        self.bucket_name = bucket_name
        self.agent_crud_service = agent_crud_service
        self.tool_loader = tool_loader
        self.cache_ttl = 3600  # 1 hour for workflows

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
                    f'Fetching and building agent for validation: namespace={namespace}, agent_name={agent_name}'
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

                # Build agent
                agent = AgentBuilder.from_yaml(
                    yaml_str=agent_yaml_content,
                    tool_registry=tool_registry,
                    access_token=access_token,
                    app_key=app_key,
                ).build()

                agents_dict[agent_ref] = agent
                logger.info(f'Successfully built agent for validation: {agent_ref}')

            except Exception as e:
                logger.error(f'Error building referenced agent {agent_ref}: {str(e)}')
                raise ValueError(
                    f'Failed to build referenced agent {agent_ref}: {str(e)}'
                )

        return agents_dict

    async def _validate_yaml_content(
        self,
        yaml_content: str,
        namespace: str,
        workflow_name: str,
        access_token: Optional[str] = None,
        app_key: Optional[str] = None,
    ) -> None:
        """
        Validate YAML content by attempting to build a workflow from it

        Args:
            yaml_content: The YAML content to validate
            namespace: The namespace for logging purposes
            workflow_name: The workflow name for logging purposes

        Raises:
            ValueError: If YAML is invalid or workflow cannot be built
        """
        try:
            # Extract and build referenced agents
            agent_references = self._extract_agent_references(yaml_content)
            agents_dict = {}

            if agent_references:
                logger.info(
                    f'Building {len(agent_references)} referenced agents for validation'
                )
                agents_dict = await self._build_referenced_agents(
                    agent_references, access_token, app_key
                )

            # Validate workflow with pre-built agents
            arium_instance = AriumBuilder.from_yaml(
                yaml_str=yaml_content,
                agents=agents_dict,
                function_registry=FUNCTION_NODE_REGISTRY,
                access_token=access_token,
                app_key=app_key,
            ).build()

            # compile to verify whether the graph is correct
            arium_instance.compile()

            logger.info(
                f'YAML validation successful for namespace: {namespace}, workflow: {workflow_name}'
            )
        except Exception as e:
            logger.error(
                f'YAML validation failed for namespace: {namespace}, workflow: {workflow_name}: {str(e)}'
            )
            raise ValueError(f'Invalid workflow YAML configuration: {str(e)}')

    async def create_workflow(
        self,
        name: str,
        namespace: str,
        yaml_content: str,
        access_token: Optional[str] = None,
        app_key: Optional[str] = None,
    ) -> dict:
        """
        Create a new workflow (DB + cloud storage)

        Args:
            name: The workflow name
            namespace: The namespace name (will be created if doesn't exist)
            yaml_content: YAML configuration content

        Returns:
            dict: Created workflow details including YAML content

        Raises:
            ValueError: If workflow already exists or validation fails
        """
        logger.info(f'Creating workflow - namespace: {namespace}, name: {name}')

        # Validate workflow name
        validate_agent_workflow_name(name, type='workflow')

        # Validate YAML content before proceeding
        await self._validate_yaml_content(
            yaml_content, namespace, name, access_token, app_key
        )

        # Get or create namespace first
        namespace_dict = await self.namespace_service.get_or_create_namespace(namespace)

        # Check if workflow with this name already exists in this namespace
        existing_workflow = await self.workflow_repository.find_one(
            name=name, namespace=namespace_dict['name']
        )
        if existing_workflow:
            logger.warning(
                f'Workflow already exists with name: {name} in namespace: {namespace_dict["name"]}'
            )
            raise ValueError(
                f'Workflow already exists with name: {name} in namespace: {namespace_dict["name"]}'
            )

        # Create workflow record in DB
        workflow = await self.workflow_repository.create(
            name=name, namespace=namespace_dict['name']
        )

        # Upload YAML to cloud storage
        yaml_key = get_workflow_yaml_key(namespace, name)
        yaml_bytes = yaml_content.encode('utf-8')
        self.cloud_storage_manager.save_small_file(
            file_content=yaml_bytes, bucket_name=self.bucket_name, key=yaml_key
        )

        # Build response with YAML content
        workflow_dict = workflow.to_dict()
        workflow_dict['yaml_content'] = yaml_content

        # Cache workflow metadata
        workflow_cache_key = get_workflow_by_id_cache_key(workflow.id)
        self.cache_manager.add(
            workflow_cache_key, json.dumps(workflow.to_dict()), expiry=self.cache_ttl
        )

        # Cache YAML content
        yaml_cache_key = get_workflow_yaml_cache_key(namespace, name)
        self.cache_manager.add(yaml_cache_key, yaml_content, expiry=self.cache_ttl)

        # Invalidate list caches
        self.cache_manager.remove(get_workflows_list_cache_key(None))
        self.cache_manager.remove(get_workflows_list_cache_key(namespace))

        logger.info(
            f'Successfully created workflow - namespace: {namespace}, name: {name}'
        )
        return workflow_dict

    async def get_workflow(self, workflow_id: UUID) -> dict:
        """
        Get workflow by ID with YAML content

        Args:
            workflow_id: The workflow UUID

        Returns:
            dict: Workflow details including YAML content

        Raises:
            ValueError: If workflow not found
        """
        # Try cache first
        cache_key = get_workflow_by_id_cache_key(workflow_id)
        cached_workflow = self.cache_manager.get_str(cache_key)

        if cached_workflow:
            logger.info(f'Cache hit for workflow ID: {workflow_id}')
            workflow_dict = json.loads(cached_workflow)
        else:
            # Fetch from DB
            logger.info(f'Fetching workflow from DB - ID: {workflow_id}')
            workflow = await self.workflow_repository.find_one(id=workflow_id)

            if not workflow:
                raise ValueError(f'Workflow not found with ID: {workflow_id}')

            workflow_dict = workflow.to_dict()

            # Cache workflow metadata
            self.cache_manager.add(
                cache_key, json.dumps(workflow_dict), expiry=self.cache_ttl
            )

        # Fetch YAML from cloud storage (with caching)
        yaml_cache_key = get_workflow_yaml_cache_key(
            workflow_dict['namespace'], workflow_dict['name']
        )
        cached_yaml = self.cache_manager.get_str(yaml_cache_key)

        if cached_yaml:
            logger.info(
                f'Cache hit for workflow YAML - namespace: {workflow_dict["namespace"]}, name: {workflow_dict["name"]}'
            )
            yaml_content = cached_yaml
        else:
            # Fetch YAML from cloud storage
            yaml_key = get_workflow_yaml_key(
                workflow_dict['namespace'], workflow_dict['name']
            )
            logger.info(f'Fetching workflow YAML from storage - key: {yaml_key}')

            try:
                yaml_bytes = self.cloud_storage_manager.read_file(
                    self.bucket_name, yaml_key
                )
                yaml_content = yaml_bytes.decode('utf-8')

                # Cache YAML
                self.cache_manager.add(
                    yaml_cache_key, yaml_content, expiry=self.cache_ttl
                )
            except CloudStorageFileNotFoundError:
                logger.error(
                    f'YAML not found in cloud storage for workflow ID: {workflow_id}'
                )
                raise ValueError(
                    f'Workflow YAML not found for workflow ID: {workflow_id}'
                )

        # Add YAML to response
        workflow_dict['yaml_content'] = yaml_content

        logger.info(f'Successfully retrieved workflow - ID: {workflow_id}')
        return workflow_dict

    async def update_workflow(
        self,
        workflow_id: UUID,
        yaml_content: str,
        access_token: Optional[str] = None,
        app_key: Optional[str] = None,
    ) -> dict:
        """
        Update existing workflow YAML configuration

        Args:
            workflow_id: The workflow UUID
            yaml_content: Updated YAML configuration content

        Returns:
            dict: Updated workflow details

        Raises:
            ValueError: If workflow not found or validation fails
        """
        logger.info(f'Updating workflow - ID: {workflow_id}')

        # Fetch workflow from DB
        workflow = await self.workflow_repository.find_one(id=workflow_id)
        if not workflow:
            raise ValueError(f'Workflow not found with ID: {workflow_id}')

        # Validate YAML content
        await self._validate_yaml_content(
            yaml_content, workflow.namespace, workflow.name, access_token, app_key
        )

        # Update YAML in cloud storage
        yaml_key = get_workflow_yaml_key(workflow.namespace, workflow.name)
        yaml_bytes = yaml_content.encode('utf-8')
        self.cloud_storage_manager.save_small_file(
            file_content=yaml_bytes, bucket_name=self.bucket_name, key=yaml_key
        )

        # Update workflow timestamp in DB (triggers updated_at)
        updated_workflow = await self.workflow_repository.find_one_and_update(
            {'id': workflow_id}, refresh=True
        )

        # Invalidate caches
        workflow_cache_key = get_workflow_by_id_cache_key(workflow_id)
        self.cache_manager.remove(workflow_cache_key)

        yaml_cache_key = get_workflow_yaml_cache_key(workflow.namespace, workflow.name)
        self.cache_manager.remove(yaml_cache_key)

        # Invalidate list caches
        self.cache_manager.remove(get_workflows_list_cache_key(None))
        self.cache_manager.remove(get_workflows_list_cache_key(workflow.namespace))

        # Build response
        workflow_dict = updated_workflow.to_dict()
        workflow_dict['yaml_content'] = yaml_content

        logger.info(f'Successfully updated workflow - ID: {workflow_id}')
        return workflow_dict

    async def delete_workflow(self, workflow_id: UUID) -> bool:
        """
        Delete workflow (DB + cloud storage)

        Args:
            workflow_id: The workflow UUID

        Returns:
            bool: Success status

        Raises:
            ValueError: If workflow not found
        """
        logger.info(f'Deleting workflow - ID: {workflow_id}')

        # Fetch workflow from DB
        workflow = await self.workflow_repository.find_one(id=workflow_id)
        if not workflow:
            raise ValueError(f'Workflow not found with ID: {workflow_id}')

        # Delete from DB
        await self.workflow_repository.delete_all(id=workflow_id)

        # Delete YAML from cloud storage
        yaml_key = get_workflow_yaml_key(workflow.namespace, workflow.name)
        try:
            self.cloud_storage_manager.delete_file(self.bucket_name, yaml_key)
        except Exception as e:
            logger.error(f'Failed to delete YAML from cloud storage: {str(e)}')
            # Continue - DB record is deleted

        # Invalidate caches
        workflow_cache_key = get_workflow_by_id_cache_key(workflow_id)
        self.cache_manager.remove(workflow_cache_key)

        yaml_cache_key = get_workflow_yaml_cache_key(workflow.namespace, workflow.name)
        self.cache_manager.remove(yaml_cache_key)

        # Invalidate list caches
        self.cache_manager.remove(get_workflows_list_cache_key(None))
        self.cache_manager.remove(get_workflows_list_cache_key(workflow.namespace))

        logger.info(f'Successfully deleted workflow - ID: {workflow_id}')
        return True

    async def list_workflows(self, namespace: Optional[str] = None) -> List[dict]:
        """
        List workflows from database with optional namespace filtering

        Args:
            namespace: Optional namespace to filter workflows

        Returns:
            List[dict]: List of workflows (without YAML content)
        """
        # Try cache first
        cache_key = get_workflows_list_cache_key(namespace)
        cached_list = self.cache_manager.get_str(cache_key)

        if cached_list:
            logger.info(f'Cache hit for workflows list - namespace: {namespace}')
            return json.loads(cached_list)

        # Fetch from DB
        logger.info(f'Fetching workflows list from DB - namespace: {namespace}')

        if namespace:
            workflows = await self.workflow_repository.find(namespace=namespace)
        else:
            workflows = await self.workflow_repository.find()

        workflows_list = [workflow.to_dict() for workflow in workflows]

        # Cache the result (shorter TTL for lists)
        self.cache_manager.add(
            cache_key, json.dumps(workflows_list), expiry=1800
        )  # 30 min

        logger.info(
            f'Successfully retrieved {len(workflows_list)} workflows - namespace: {namespace}'
        )
        return workflows_list
