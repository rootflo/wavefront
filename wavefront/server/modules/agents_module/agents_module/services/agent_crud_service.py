import json
import yaml
from typing import List, Optional
from uuid import UUID

from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.models.agent import Agent
from db_repo_module.models.message_processors import MessageProcessors
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from flo_cloud.cloud_storage import CloudStorageManager
from flo_cloud.exceptions import CloudStorageFileNotFoundError
from common_module.log.logger import logger
from agents_module.services.namespace_service import NamespaceService
from agents_module.utils.agent_utils import get_agent_yaml_key
from agents_module.utils.cache_utils import (
    get_agent_by_id_cache_key,
    get_agent_yaml_cache_key,
    get_agents_list_cache_key,
)
from agents_module.utils.validation_utils import validate_agent_workflow_name
from flo_ai import AgentBuilder
from flo_ai.tool.base_tool import Tool
from tools_module.utils.api_service_tool_loader import load_api_service_tool
from api_services_module.core.manager import ApiServicesManager


class AgentCrudService:
    """Service for handling agent CRUD operations with DB + cloud storage"""

    def __init__(
        self,
        agent_repository: SQLAlchemyRepository[Agent],
        namespace_service: NamespaceService,
        cloud_storage_manager: CloudStorageManager,
        cache_manager: CacheManager,
        bucket_name: str,
        message_processor_repository: SQLAlchemyRepository[MessageProcessors],
        message_processor_bucket_name: str,
        api_services_manager: Optional[ApiServicesManager] = None,
    ):
        """
        Initialize the agent CRUD service

        Args:
            agent_repository: Agent repository for DB operations
            namespace_service: Namespace service for namespace operations
            cloud_storage_manager: Cloud storage manager instance
            cache_manager: Cache manager instance
            bucket_name: Name of the bucket containing agent YAML files
            message_processor_repository: Repository for message processors
            message_processor_bucket_name: Name of the bucket containing message processor YAML files
        """
        self.agent_repository = agent_repository
        self.namespace_service = namespace_service
        self.cloud_storage_manager = cloud_storage_manager
        self.cache_manager = cache_manager
        self.bucket_name = bucket_name
        self.message_processor_repository = message_processor_repository
        self.message_processor_bucket_name = message_processor_bucket_name
        self.api_services_manager = api_services_manager
        self.cache_ttl = 3600  # 1 hour for agents

    async def _validate_yaml_content(
        self,
        yaml_content: str,
        namespace: str,
        agent_name: str,
        tool_available: List[Tool],
        access_token: Optional[str] = None,
        app_key: Optional[str] = None,
    ) -> None:
        """
        Validate YAML content by attempting to build an agent from it

        Args:
            yaml_content: The YAML content to validate
            namespace: The namespace for logging purposes
            agent_name: The agent name for logging purposes
            tool_available: List of available tools

        Raises:
            ValueError: If YAML is invalid or agent cannot be built
        """
        try:
            yaml_data = yaml.safe_load(yaml_content)
            yaml_tools = yaml_data.get('agent', {}).get('tools', None)
            tool_registry = {}
            if yaml_tools:
                for tool in yaml_tools:
                    tool_name = tool.get('name', None)
                    if tool_name:
                        # First, try to find in tool_available list
                        tool_found = False
                        for tool_obj in tool_available:
                            if tool_obj.name == tool_name:
                                tool_registry[tool_name] = tool_obj
                                tool_found = True
                                break

                        # If not found, check if it's a message processor
                        if not tool_found:
                            tool_obj = await self._try_load_message_processor_tool(
                                tool_name
                            )
                            if tool_obj:
                                tool_registry[tool_name] = tool_obj
                                tool_found = True

                        # If still not found, try loading as API service
                        if not tool_found:
                            tool_obj = await self._try_load_api_service_tool(tool_name)
                            if tool_obj:
                                tool_registry[tool_name] = tool_obj
                                tool_found = True

                        # If still not found, log warning (AgentBuilder will fail with better error)
                        if not tool_found:
                            logger.warning(
                                f'Tool {tool_name} not found in available tools, message processors, or API services'
                            )

            AgentBuilder.from_yaml(
                yaml_str=yaml_content,
                tool_registry=tool_registry,
                access_token=access_token,
                app_key=app_key,
            ).build()
            logger.info(
                f'YAML validation successful for namespace: {namespace}, agent: {agent_name}'
            )
        except Exception as e:
            logger.error(
                f'YAML validation failed for namespace: {namespace}, agent: {agent_name}: {str(e)}'
            )
            raise ValueError(f'Invalid agent YAML configuration: {str(e)}')

    async def _try_load_message_processor_tool(self, tool_name: str) -> Optional[Tool]:
        """
        Attempt to load a message processor as a Tool object.

        Args:
            tool_name: Name of the tool (should match message processor name)

        Returns:
            Tool object if message processor found, None otherwise
        """
        from tools_module.utils.message_processor_fn import execute_message_processor_fn

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

    async def create_agent(
        self,
        name: str,
        namespace: str,
        yaml_content: str,
        tool_available: List[Tool],
        access_token: Optional[str] = None,
        app_key: Optional[str] = None,
    ) -> dict:
        """
        Create a new agent (DB + cloud storage)

        Args:
            name: The agent name
            namespace: The namespace name (will be created if doesn't exist)
            yaml_content: YAML configuration content
            tool_available: List of available tools

        Returns:
            dict: Created agent details including YAML content

        Raises:
            ValueError: If agent already exists or validation fails
        """
        logger.info(f'Creating agent - namespace: {namespace}, name: {name}')

        # Validate agent name
        validate_agent_workflow_name(name, type='agent')

        # Validate YAML content before proceeding
        await self._validate_yaml_content(
            yaml_content, namespace, name, tool_available, access_token, app_key
        )

        # Get or create namespace first
        namespace_dict = await self.namespace_service.get_or_create_namespace(namespace)

        # Check if agent with this name already exists in this namespace
        existing_agent = await self.agent_repository.find_one(
            name=name, namespace=namespace_dict['name']
        )
        if existing_agent:
            logger.warning(
                f'Agent already exists with name: {name} in namespace: {namespace_dict["name"]}'
            )
            raise ValueError(
                f'Agent already exists with name: {name} in namespace: {namespace_dict["name"]}'
            )

        # Create agent record in DB
        agent = await self.agent_repository.create(
            name=name, namespace=namespace_dict['name']
        )

        # Upload YAML to cloud storage
        yaml_key = get_agent_yaml_key(namespace, name)
        yaml_bytes = yaml_content.encode('utf-8')
        self.cloud_storage_manager.save_small_file(
            file_content=yaml_bytes, bucket_name=self.bucket_name, key=yaml_key
        )

        # Build response with YAML content
        agent_dict = agent.to_dict()
        agent_dict['yaml_content'] = yaml_content

        # Cache agent metadata
        agent_cache_key = get_agent_by_id_cache_key(agent.id)
        self.cache_manager.add(
            agent_cache_key, json.dumps(agent.to_dict()), expiry=self.cache_ttl
        )

        # Cache YAML content
        yaml_cache_key = get_agent_yaml_cache_key(namespace, name)
        self.cache_manager.add(yaml_cache_key, yaml_content, expiry=self.cache_ttl)

        # Invalidate list caches
        self.cache_manager.remove(get_agents_list_cache_key(None))
        self.cache_manager.remove(get_agents_list_cache_key(namespace))

        logger.info(
            f'Successfully created agent - namespace: {namespace}, name: {name}'
        )
        return agent_dict

    async def get_agent(self, agent_id: UUID) -> dict:
        """
        Get agent by ID with YAML content

        Args:
            agent_id: The agent UUID

        Returns:
            dict: Agent details including YAML content

        Raises:
            ValueError: If agent not found
        """
        # Try cache first
        cache_key = get_agent_by_id_cache_key(agent_id)
        cached_agent = self.cache_manager.get_str(cache_key)

        if cached_agent:
            logger.info(f'Cache hit for agent ID: {agent_id}')
            agent_dict = json.loads(cached_agent)
        else:
            # Fetch from DB
            logger.info(f'Fetching agent from DB - ID: {agent_id}')
            agent = await self.agent_repository.find_one(id=agent_id)

            if not agent:
                raise ValueError(f'Agent not found with ID: {agent_id}')

            agent_dict = agent.to_dict()

            # Cache agent metadata
            self.cache_manager.add(
                cache_key, json.dumps(agent_dict), expiry=self.cache_ttl
            )

        # Fetch YAML from cloud storage (with caching)
        yaml_cache_key = get_agent_yaml_cache_key(
            agent_dict['namespace'], agent_dict['name']
        )
        cached_yaml = self.cache_manager.get_str(yaml_cache_key)

        if cached_yaml:
            logger.info(
                f'Cache hit for agent YAML - namespace: {agent_dict["namespace"]}, name: {agent_dict["name"]}'
            )
            yaml_content = cached_yaml
        else:
            # Fetch YAML from cloud storage
            yaml_key = get_agent_yaml_key(agent_dict['namespace'], agent_dict['name'])
            logger.info(f'Fetching agent YAML from storage - key: {yaml_key}')

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
                    f'YAML not found in cloud storage for agent ID: {agent_id}'
                )
                raise ValueError(f'Agent YAML not found for agent ID: {agent_id}')

        # Add YAML to response
        agent_dict['yaml_content'] = yaml_content

        logger.info(f'Successfully retrieved agent - ID: {agent_id}')
        return agent_dict

    async def get_agent_yaml_from_bucket(self, agent_name: str, namespace: str) -> str:
        """
        Get agent YAML content by name and namespace (for workflow references)

        This method is used by workflow services to fetch agent YAML when they
        have namespace/agent_name references

        Args:
            agent_name: The agent name
            namespace: The namespace name

        Returns:
            str: The YAML content as string

        Raises:
            ValueError: If agent not found
        """
        # Try YAML cache first
        yaml_cache_key = get_agent_yaml_cache_key(namespace, agent_name)
        cached_yaml = self.cache_manager.get_str(yaml_cache_key)

        if cached_yaml:
            logger.info(
                f'Cache hit for agent YAML - namespace: {namespace}, name: {agent_name}'
            )
            return cached_yaml

        # Fetch YAML from cloud storage
        yaml_key = get_agent_yaml_key(namespace, agent_name)
        logger.info(f'Fetching agent YAML from storage - key: {yaml_key}')

        try:
            yaml_bytes = self.cloud_storage_manager.read_file(
                self.bucket_name, yaml_key
            )
            yaml_content = yaml_bytes.decode('utf-8')

            # Cache YAML
            self.cache_manager.add(yaml_cache_key, yaml_content, expiry=self.cache_ttl)
        except CloudStorageFileNotFoundError:
            logger.error(
                f'YAML not found in cloud storage for agent: {namespace}/{agent_name}'
            )
            raise ValueError(
                f'Agent YAML not found for agent: {namespace}/{agent_name}'
            )

        logger.info(
            f'Successfully retrieved agent YAML - namespace: {namespace}, name: {agent_name}'
        )
        return yaml_content

    async def update_agent(
        self,
        agent_id: UUID,
        yaml_content: str,
        tool_available: List[Tool],
        access_token: Optional[str] = None,
        app_key: Optional[str] = None,
    ) -> dict:
        """
        Update existing agent YAML configuration

        Args:
            agent_id: The agent UUID
            yaml_content: Updated YAML configuration content
            tool_available: List of available tools

        Returns:
            dict: Updated agent details

        Raises:
            ValueError: If agent not found or validation fails
        """
        logger.info(f'Updating agent - ID: {agent_id}')

        # Fetch agent from DB
        agent = await self.agent_repository.find_one(id=agent_id)
        if not agent:
            raise ValueError(f'Agent not found with ID: {agent_id}')

        # Validate YAML content
        await self._validate_yaml_content(
            yaml_content,
            agent.namespace,
            agent.name,
            tool_available,
            access_token,
            app_key,
        )

        # Update YAML in cloud storage
        yaml_key = get_agent_yaml_key(agent.namespace, agent.name)
        yaml_bytes = yaml_content.encode('utf-8')
        self.cloud_storage_manager.save_small_file(
            file_content=yaml_bytes, bucket_name=self.bucket_name, key=yaml_key
        )

        # Update agent timestamp in DB (triggers updated_at)
        updated_agent = await self.agent_repository.find_one_and_update(
            {'id': agent_id}, refresh=True
        )

        # Invalidate caches
        agent_cache_key = get_agent_by_id_cache_key(agent_id)
        self.cache_manager.remove(agent_cache_key)

        yaml_cache_key = get_agent_yaml_cache_key(agent.namespace, agent.name)
        self.cache_manager.remove(yaml_cache_key)

        # Invalidate list caches
        self.cache_manager.remove(get_agents_list_cache_key(None))
        self.cache_manager.remove(get_agents_list_cache_key(agent.namespace))

        # Build response
        agent_dict = updated_agent.to_dict()
        agent_dict['yaml_content'] = yaml_content

        logger.info(f'Successfully updated agent - ID: {agent_id}')
        return agent_dict

    async def delete_agent(self, agent_id: UUID) -> bool:
        """
        Delete agent (DB + cloud storage)

        Args:
            agent_id: The agent UUID

        Returns:
            bool: Success status

        Raises:
            ValueError: If agent not found
        """
        logger.info(f'Deleting agent - ID: {agent_id}')

        # Fetch agent from DB
        agent = await self.agent_repository.find_one(id=agent_id)
        if not agent:
            raise ValueError(f'Agent not found with ID: {agent_id}')

        # Delete from DB
        await self.agent_repository.delete_all(id=agent_id)

        # Delete YAML from cloud storage
        yaml_key = get_agent_yaml_key(agent.namespace, agent.name)
        try:
            self.cloud_storage_manager.delete_file(self.bucket_name, yaml_key)
        except Exception as e:
            logger.error(f'Failed to delete YAML from cloud storage: {str(e)}')
            # Continue - DB record is deleted

        # Invalidate caches
        agent_cache_key = get_agent_by_id_cache_key(agent_id)
        self.cache_manager.remove(agent_cache_key)

        yaml_cache_key = get_agent_yaml_cache_key(agent.namespace, agent.name)
        self.cache_manager.remove(yaml_cache_key)

        # Invalidate list caches
        self.cache_manager.remove(get_agents_list_cache_key(None))
        self.cache_manager.remove(get_agents_list_cache_key(agent.namespace))

        logger.info(f'Successfully deleted agent - ID: {agent_id}')
        return True

    async def list_agents(self, namespace: Optional[str] = None) -> List[dict]:
        """
        List agents from database with optional namespace filtering

        Args:
            namespace: Optional namespace to filter agents

        Returns:
            List[dict]: List of agents (without YAML content)
        """
        # Try cache first
        cache_key = get_agents_list_cache_key(namespace)
        cached_list = self.cache_manager.get_str(cache_key)

        if cached_list:
            logger.info(f'Cache hit for agents list - namespace: {namespace}')
            return json.loads(cached_list)

        # Fetch from DB
        logger.info(f'Fetching agents list from DB - namespace: {namespace}')

        if namespace:
            agents = await self.agent_repository.find(namespace=namespace)
        else:
            agents = await self.agent_repository.find()

        agents_list = [agent.to_dict() for agent in agents]

        # Cache the result (shorter TTL for lists)
        self.cache_manager.add(
            cache_key, json.dumps(agents_list), expiry=1800
        )  # 30 min

        logger.info(
            f'Successfully retrieved {len(agents_list)} agents - namespace: {namespace}'
        )
        return agents_list
