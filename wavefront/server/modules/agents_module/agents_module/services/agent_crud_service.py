import asyncio
import json
import yaml
from typing import List, Optional
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.models.agent import Agent
from db_repo_module.models.agent_version import AgentVersion
from db_repo_module.models.message_processors import MessageProcessors
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from flo_cloud.cloud_storage import CloudStorageManager
from flo_cloud.exceptions import CloudStorageFileNotFoundError
from common_module.log.logger import logger
from agents_module.services.namespace_service import NamespaceService
from agents_module.utils.agent_utils import get_agent_yaml_key
from agents_module.utils.cache_utils import (
    get_agent_by_id_cache_key,
    get_agent_current_version_cache_key,
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
        agent_version_repository: SQLAlchemyRepository[AgentVersion],
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
            agent_version_repository: AgentVersion repository for per-version DB operations
            namespace_service: Namespace service for namespace operations
            cloud_storage_manager: Cloud storage manager instance
            cache_manager: Cache manager instance
            bucket_name: Name of the bucket containing agent YAML files
            message_processor_repository: Repository for message processors
            message_processor_bucket_name: Name of the bucket containing message processor YAML files
        """
        self.agent_repository = agent_repository
        self.agent_version_repository = agent_version_repository
        self.namespace_service = namespace_service
        self.cloud_storage_manager = cloud_storage_manager
        self.cache_manager = cache_manager
        self.bucket_name = bucket_name
        self.message_processor_repository = message_processor_repository
        self.message_processor_bucket_name = message_processor_bucket_name
        self.api_services_manager = api_services_manager
        self.cache_ttl = 3600  # 1 hour for agents
        self.current_version_cache_ttl = (
            60  # short TTL for name-based version resolution
        )

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

        # Create agent identity row, then its first version row. These are two
        # separate, non-atomic calls; if the second one fails, compensate by
        # removing the identity row rather than leaving an orphaned agent with
        # zero versions that would permanently block this (name, namespace) pair.
        agent = await self.agent_repository.create(
            name=name, namespace=namespace_dict['name'], current_version=1
        )
        try:
            await self.agent_version_repository.create(
                agent_id=agent.id, version=1, is_deleted=False
            )
        except Exception:
            logger.error(
                f'Failed to create first version for agent {agent.id} - rolling back identity row'
            )
            await self.agent_repository.delete_all(id=agent.id)
            raise

        # Upload YAML to cloud storage
        yaml_key = get_agent_yaml_key(namespace, name, 1)
        yaml_bytes = yaml_content.encode('utf-8')
        self.cloud_storage_manager.save_small_file(
            file_content=yaml_bytes,
            bucket_name=self.bucket_name,
            key=yaml_key,
            disable_cache=True,
        )

        # Build response with YAML content
        agent_dict = agent.to_dict()
        agent_dict['version'] = 1
        agent_dict['yaml_content'] = yaml_content

        # Cache agent metadata
        agent_cache_key = get_agent_by_id_cache_key(agent.id)
        self.cache_manager.add(
            agent_cache_key, json.dumps(agent.to_dict()), expiry=self.cache_ttl
        )

        # Cache YAML content
        yaml_cache_key = get_agent_yaml_cache_key(namespace, name, 1)
        self.cache_manager.add(yaml_cache_key, yaml_content, expiry=self.cache_ttl)

        # Invalidate list caches
        self.cache_manager.remove(get_agents_list_cache_key(None))
        self.cache_manager.remove(get_agents_list_cache_key(namespace))

        logger.info(
            f'Successfully created agent - namespace: {namespace}, name: {name}'
        )
        return agent_dict

    async def get_agent(self, agent_id: UUID, version: Optional[int] = None) -> dict:
        """
        Get agent by ID with YAML content

        Args:
            agent_id: The agent UUID
            version: Specific version to fetch; defaults to the agent's current_version

        Returns:
            dict: Agent details including YAML content, with 'version' set to
                whichever version was actually resolved

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

        resolved_version = (
            version if version is not None else agent_dict['current_version']
        )

        if version is not None:
            version_row = await self.agent_version_repository.find_one(
                agent_id=agent_id, version=version
            )
            if not version_row or version_row.is_deleted:
                raise ValueError(
                    f'Agent YAML not found for agent ID: {agent_id}, version: {version}'
                )

        # Fetch YAML from cloud storage (with caching)
        yaml_cache_key = get_agent_yaml_cache_key(
            agent_dict['namespace'], agent_dict['name'], resolved_version
        )
        cached_yaml = self.cache_manager.get_str(yaml_cache_key)

        if cached_yaml:
            logger.info(
                f'Cache hit for agent YAML - namespace: {agent_dict["namespace"]}, name: {agent_dict["name"]}, version: {resolved_version}'
            )
            yaml_content = cached_yaml
        else:
            # Fetch YAML from cloud storage
            yaml_key = get_agent_yaml_key(
                agent_dict['namespace'], agent_dict['name'], resolved_version
            )
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
                    f'YAML not found in cloud storage for agent ID: {agent_id}, version: {resolved_version}'
                )
                raise ValueError(
                    f'Agent YAML not found for agent ID: {agent_id}, version: {resolved_version}'
                )

        # Add version/YAML to response
        agent_dict['version'] = resolved_version
        agent_dict['yaml_content'] = yaml_content

        logger.info(
            f'Successfully retrieved agent - ID: {agent_id}, version: {resolved_version}'
        )
        return agent_dict

    async def _resolve_agent_current_version(
        self, agent_name: str, namespace: str
    ) -> int:
        """
        Resolve current_version for an agent by name+namespace, via a short-TTL cache
        so name-based lookups (no explicit version) don't hit the DB on every call.
        """
        cache_key = get_agent_current_version_cache_key(namespace, agent_name)
        cached_version = self.cache_manager.get_str(cache_key)
        if cached_version:
            return int(cached_version)

        agent = await self.agent_repository.find_one(
            name=agent_name, namespace=namespace
        )
        if not agent:
            raise ValueError(f'Agent not found: {namespace}/{agent_name}')

        self.cache_manager.add(
            cache_key, str(agent.current_version), expiry=self.current_version_cache_ttl
        )
        return agent.current_version

    async def get_agent_yaml_from_bucket(
        self, agent_name: str, namespace: str, version: Optional[int] = None
    ) -> str:
        """
        Get agent YAML content by name and namespace (for workflow references)

        This method is used by workflow services to fetch agent YAML when they
        have namespace/agent_name references

        Args:
            agent_name: The agent name
            namespace: The namespace name
            version: Specific version to fetch; defaults to the agent's current_version

        Returns:
            str: The YAML content as string

        Raises:
            ValueError: If agent not found
        """
        resolved_version = version
        if resolved_version is None:
            resolved_version = await self._resolve_agent_current_version(
                agent_name, namespace
            )
        else:
            agent = await self.agent_repository.find_one(
                name=agent_name, namespace=namespace
            )
            if not agent:
                raise ValueError(f'Agent not found: {namespace}/{agent_name}')
            version_row = await self.agent_version_repository.find_one(
                agent_id=agent.id, version=resolved_version
            )
            if not version_row or version_row.is_deleted:
                raise ValueError(
                    f'Agent YAML not found for agent: {namespace}/{agent_name}, version: {resolved_version}'
                )

        # Try YAML cache first
        yaml_cache_key = get_agent_yaml_cache_key(
            namespace, agent_name, resolved_version
        )
        cached_yaml = self.cache_manager.get_str(yaml_cache_key)

        if cached_yaml:
            logger.info(
                f'Cache hit for agent YAML - namespace: {namespace}, name: {agent_name}, version: {resolved_version}'
            )
            return cached_yaml

        # Fetch YAML from cloud storage
        yaml_key = get_agent_yaml_key(namespace, agent_name, resolved_version)
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
                f'YAML not found in cloud storage for agent: {namespace}/{agent_name}, version: {resolved_version}'
            )
            raise ValueError(
                f'Agent YAML not found for agent: {namespace}/{agent_name}, version: {resolved_version}'
            )

        logger.info(
            f'Successfully retrieved agent YAML - namespace: {namespace}, name: {agent_name}, version: {resolved_version}'
        )
        return yaml_content

    async def update_agent(
        self,
        agent_id: UUID,
        yaml_content: str,
        tool_available: List[Tool],
        access_token: Optional[str] = None,
        app_key: Optional[str] = None,
        version: Optional[int] = None,
        create_new_version: bool = False,
    ) -> dict:
        """
        Update an agent's YAML configuration - either in place, or as a new version

        Args:
            agent_id: The agent UUID
            yaml_content: Updated YAML configuration content
            tool_available: List of available tools
            version: Which existing version to edit in place, or branch a new version
                from; defaults to the agent's current_version
            create_new_version: If True, create a new version instead of editing
                `version` in place. The new version never becomes current_version
                automatically - it must be explicitly promoted.

        Returns:
            dict: Updated agent details, with 'version' set to whichever version
                was actually written

        Raises:
            ValueError: If agent (or the target version) not found, or validation fails
        """
        logger.info(
            f'Updating agent - ID: {agent_id}, version: {version}, create_new_version: {create_new_version}'
        )

        # Fetch agent from DB
        agent = await self.agent_repository.find_one(id=agent_id)
        if not agent:
            raise ValueError(f'Agent not found with ID: {agent_id}')

        target_version = version if version is not None else agent.current_version

        # Validate YAML content
        await self._validate_yaml_content(
            yaml_content,
            agent.namespace,
            agent.name,
            tool_available,
            access_token,
            app_key,
        )

        if create_new_version:
            existing_versions = await self.agent_version_repository.find(
                agent_id=agent.id, limit=100000
            )
            source_version = next(
                (v for v in existing_versions if v.version == target_version), None
            )
            if not source_version or source_version.is_deleted:
                raise ValueError(
                    f'Agent {agent_id} has no version {target_version} to branch from'
                )
            write_version = max(v.version for v in existing_versions) + 1
            try:
                await self.agent_version_repository.create(
                    agent_id=agent.id, version=write_version, is_deleted=False
                )
            except IntegrityError:
                # Another concurrent create_new_version call already took write_version.
                raise ValueError(
                    f'Concurrent version creation conflict for agent {agent_id} - please retry'
                )
        else:
            existing_version = await self.agent_version_repository.find_one(
                agent_id=agent.id, version=target_version
            )
            if not existing_version or existing_version.is_deleted:
                raise ValueError(
                    f'Agent {agent_id} has no version {target_version} to update'
                )
            write_version = target_version

        # Write YAML to cloud storage at the resolved version's key
        yaml_key = get_agent_yaml_key(agent.namespace, agent.name, write_version)
        yaml_bytes = yaml_content.encode('utf-8')
        self.cloud_storage_manager.save_small_file(
            file_content=yaml_bytes,
            bucket_name=self.bucket_name,
            key=yaml_key,
            disable_cache=True,
        )

        # Invalidate caches
        yaml_cache_key = get_agent_yaml_cache_key(
            agent.namespace, agent.name, write_version
        )
        self.cache_manager.remove(yaml_cache_key)

        # Invalidate list caches
        self.cache_manager.remove(get_agents_list_cache_key(None))
        self.cache_manager.remove(get_agents_list_cache_key(agent.namespace))

        # Build response
        agent_dict = agent.to_dict()
        agent_dict['version'] = write_version
        agent_dict['yaml_content'] = yaml_content

        logger.info(
            f'Successfully updated agent - ID: {agent_id}, version: {write_version}'
        )
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

        # Fetch every version so we can clean up storage/caches for each of them
        # before the identity row (and, via FK cascade, the version rows) are deleted.
        versions = await self.agent_version_repository.find(
            agent_id=agent.id, limit=100000
        )

        # Delete from DB (cascades to agent_versions)
        await self.agent_repository.delete_all(id=agent_id)

        async def _delete_version_yaml(version: int) -> None:
            yaml_key = get_agent_yaml_key(agent.namespace, agent.name, version)
            try:
                await asyncio.to_thread(
                    self.cloud_storage_manager.delete_file, self.bucket_name, yaml_key
                )
            except Exception as e:
                logger.error(f'Failed to delete YAML from cloud storage: {str(e)}')
                # Continue - DB record is deleted

            yaml_cache_key = get_agent_yaml_cache_key(
                agent.namespace, agent.name, version
            )
            self.cache_manager.remove(yaml_cache_key)

        await asyncio.gather(*(_delete_version_yaml(v.version) for v in versions))

        # Invalidate caches
        agent_cache_key = get_agent_by_id_cache_key(agent_id)
        self.cache_manager.remove(agent_cache_key)
        self.cache_manager.remove(
            get_agent_current_version_cache_key(agent.namespace, agent.name)
        )

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

    async def promote_agent_version(self, agent_id: UUID, version: int) -> dict:
        """
        Make an existing version the agent's current_version

        Args:
            agent_id: The agent UUID
            version: The version to promote

        Returns:
            dict: Updated agent details

        Raises:
            ValueError: If agent not found, or the version doesn't exist / is deleted
        """
        logger.info(f'Promoting agent {agent_id} to version {version}')

        agent = await self.agent_repository.find_one(id=agent_id)
        if not agent:
            raise ValueError(f'Agent not found with ID: {agent_id}')

        target_version = await self.agent_version_repository.find_one(
            agent_id=agent.id, version=version
        )
        if not target_version or target_version.is_deleted:
            raise ValueError(
                f'Agent {agent_id} has no live version {version} to promote'
            )

        updated_agent = await self.agent_repository.find_one_and_update(
            {'id': agent_id}, current_version=version, refresh=True
        )

        self.cache_manager.remove(get_agent_by_id_cache_key(agent_id))
        self.cache_manager.remove(
            get_agent_current_version_cache_key(agent.namespace, agent.name)
        )
        self.cache_manager.remove(get_agents_list_cache_key(None))
        self.cache_manager.remove(get_agents_list_cache_key(agent.namespace))

        logger.info(f'Successfully promoted agent {agent_id} to version {version}')
        return updated_agent.to_dict()

    async def list_agent_versions(self, agent_id: UUID) -> List[dict]:
        """
        List every live (non-deleted) version of an agent

        Args:
            agent_id: The agent UUID

        Returns:
            List[dict]: Versions sorted ascending, each annotated with 'is_current'

        Raises:
            ValueError: If agent not found
        """
        agent = await self.agent_repository.find_one(id=agent_id)
        if not agent:
            raise ValueError(f'Agent not found with ID: {agent_id}')

        versions = await self.agent_version_repository.find(
            agent_id=agent.id, limit=100000
        )

        version_dicts = []
        for agent_version in sorted(versions, key=lambda v: v.version):
            if agent_version.is_deleted:
                continue
            version_dict = agent_version.to_dict()
            version_dict['is_current'] = agent_version.version == agent.current_version
            version_dicts.append(version_dict)

        return version_dicts

    async def delete_agent_version(self, agent_id: UUID, version: int) -> bool:
        """
        Soft-delete a single version of an agent

        The current_version is never left dangling: deleting the version that is
        currently current_version is rejected until a different version is
        promoted first. Version numbers are never reused.

        Args:
            agent_id: The agent UUID
            version: The version to delete

        Returns:
            bool: Success status

        Raises:
            ValueError: If agent/version not found, or version is the current_version
        """
        logger.info(f'Deleting agent {agent_id} version {version}')

        agent = await self.agent_repository.find_one(id=agent_id)
        if not agent:
            raise ValueError(f'Agent not found with ID: {agent_id}')

        if version == agent.current_version:
            raise ValueError(
                f'Cannot delete version {version} of agent {agent_id} because it is '
                'the current version - promote a different version first'
            )

        target_version = await self.agent_version_repository.find_one(
            agent_id=agent.id, version=version
        )
        if not target_version or target_version.is_deleted:
            raise ValueError(
                f'Agent {agent_id} has no live version {version} to delete'
            )

        await self.agent_version_repository.find_one_and_update(
            {'agent_id': agent.id, 'version': version}, is_deleted=True
        )

        self.cache_manager.remove(
            get_agent_yaml_cache_key(agent.namespace, agent.name, version)
        )

        logger.info(f'Successfully deleted agent {agent_id} version {version}')
        return True
