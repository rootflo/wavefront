import asyncio
import json
import yaml
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.models.agent import Agent
from db_repo_module.models.agent_version import AgentVersion
from db_repo_module.models.message_processors import MessageProcessors
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from flo_cloud.cloud_storage import CloudStorageManager
from flo_cloud.exceptions import CloudStorageFileNotFoundError
from common_module.blocking_io import BlockingPoolBusyError, run_in_pool
from common_module.log.logger import logger
from agents_module.services.namespace_service import NamespaceService
from agents_module.utils.agent_utils import get_agent_yaml_key
from agents_module.utils.cache_utils import (
    get_agent_by_id_cache_key,
    get_agent_current_version_cache_key,
    get_agent_yaml_cache_key,
    get_agents_list_cache_key,
)
from agents_module.models.yaml_validation_schemas import YamlValidationError
from agents_module.utils.validation_utils import (
    InvalidDefinitionError,
    validate_agent_workflow_name,
)
from agents_module.utils.yaml_validation import (
    format_validation_errors,
    missing_tool_error,
    parse_yaml_document,
    validate_agent_document,
)
from flo_ai import AgentBuilder
from flo_ai.tool.base_tool import Tool
from tools_module.utils.api_service_fn import execute_api_service_fn
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

    async def resolve_tool(
        self, tool_name: str, tool_available: List[Tool]
    ) -> Optional[Tool]:
        """
        Find a tool an agent YAML refers to by name.

        Looks in the available tools first, then message processors, then API
        services - the same order agents use when they run.

        Args:
            tool_name: The tool name as written in the YAML
            tool_available: List of available tools

        Returns:
            The Tool, or None if nothing by that name exists
        """
        for tool_obj in tool_available:
            if tool_obj.name == tool_name:
                return tool_obj

        tool_obj = await self._try_load_message_processor_tool(tool_name)
        if tool_obj:
            return tool_obj

        return await self._try_load_api_service_tool(tool_name)

    async def _check_yaml_content(
        self, yaml_content: str, tool_available: List[Tool]
    ) -> Tuple[List[YamlValidationError], Dict[str, Tool]]:
        """
        Validate agent YAML statically: no LLM is created and nothing is built.

        Runs flo_ai's agent model and the rules the agent build adds, then looks
        up every tool the agent names.

        Returns:
            The errors found (empty when valid) and the tools that resolved, keyed
            by name, ready to hand to AgentBuilder.
        """
        yaml_data, errors = parse_yaml_document(yaml_content)
        if yaml_data is None:
            return errors, {}

        report = validate_agent_document(yaml_data)
        errors = list(report.errors)

        resolved: Dict[str, Optional[Tool]] = {}
        for tool_ref in report.tool_refs:
            if tool_ref.name not in resolved:
                resolved[tool_ref.name] = await self.resolve_tool(
                    tool_ref.name, tool_available
                )
            if resolved[tool_ref.name] is None:
                errors.append(missing_tool_error(tool_ref))

        tool_registry = {
            name: tool_obj for name, tool_obj in resolved.items() if tool_obj
        }

        return errors, tool_registry

    async def validate_yaml(
        self, yaml_content: str, tool_available: List[Tool]
    ) -> List[YamlValidationError]:
        """
        Validate agent YAML without persisting or building anything.

        Args:
            yaml_content: The YAML content to validate
            tool_available: List of available tools

        Returns:
            Every problem found, each with the path of the offending key; empty
            when the YAML is valid. Unlike create/update this does not construct
            the LLM client, so it cannot catch a failure that only happens there.
        """
        errors, _ = await self._check_yaml_content(yaml_content, tool_available)
        return errors

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
            errors, tool_registry = await self._check_yaml_content(
                yaml_content, tool_available
            )
            if errors:
                raise ValueError(format_validation_errors(errors))

            AgentBuilder.from_yaml(
                yaml_str=yaml_content,
                tool_registry=tool_registry,
                access_token=access_token,
                app_key=app_key,
            ).build()
            logger.info(
                f'YAML validation successful for namespace: {namespace}, agent: {agent_name}'
            )
        except ValueError as e:
            logger.error(
                f'YAML validation failed for namespace: {namespace}, agent: {agent_name}: {str(e)}'
            )
            raise InvalidDefinitionError(
                f'Invalid agent YAML configuration: {str(e)}'
            ) from e
        except Exception as e:
            # Not a validation error: keep the details in the log, out of the response
            logger.exception(
                f'YAML validation failed unexpectedly for namespace: {namespace}, agent: {agent_name}'
            )
            raise InvalidDefinitionError(
                'Invalid agent YAML configuration: unknown reason'
            ) from e

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
                yaml_bytes = await run_in_pool(
                    'storage',
                    self.cloud_storage_manager.read_file,
                    self.message_processor_bucket_name,
                    yaml_key,
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

            except BlockingPoolBusyError:
                raise  # overload: a 503, not a silently missing tool
            except Exception as e:
                logger.warning(
                    f'Failed to load YAML for message processor {tool_name}: {str(e)}'
                )
                return None

        except BlockingPoolBusyError:
            raise
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
        # Only used to validate an agent's YAML, never run, so the unbound
        # function is enough (same as the message-processor tool above).
        return await load_api_service_tool(
            tool_name, self.api_services_manager, execute_api_service_fn
        )

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

        # Invalidate every key a reader could have cached for this name (e.g. a
        # "not found" current-version lookup is never cached, but lists are):
        # strict before the change, best-effort after. The new agent is cached
        # by its first read, never written here.
        async with self.cache_manager.invalidating(
            get_agents_list_cache_key(None),
            get_agents_list_cache_key(namespace),
            get_agent_current_version_cache_key(namespace, name),
            get_agent_yaml_cache_key(namespace, name, 1),
        ):
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

            # Upload YAML to cloud storage. If this fails, roll back the identity and
            # version rows (the FK cascade removes the version row) so a failed upload
            # doesn't leave an orphaned, YAML-less agent that blocks this (name,
            # namespace) pair.
            yaml_key = get_agent_yaml_key(namespace, name, 1)
            yaml_bytes = yaml_content.encode('utf-8')
            try:
                await run_in_pool(
                    'storage',
                    self.cloud_storage_manager.save_small_file,
                    file_content=yaml_bytes,
                    bucket_name=self.bucket_name,
                    key=yaml_key,
                    disable_cache=True,
                )
            except BaseException:
                # Roll back, then re-raise: a busy pool still answers 503. Also on
                # cancellation (client gone), so no YAML-less row is left behind.
                logger.error(
                    f'Failed to upload YAML for new agent {agent.id} - rolling back identity and version rows'
                )
                await self.agent_repository.delete_all(id=agent.id)
                raise

        # Build response with YAML content
        agent_dict = agent.to_dict()
        agent_dict['version'] = 1
        agent_dict['yaml_content'] = yaml_content

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

        async def load_agent() -> Optional[str]:
            agent = await self.agent_repository.find_one(id=agent_id)
            return json.dumps(agent.to_dict()) if agent else None

        cached_agent = await self.cache_manager.read_through(
            get_agent_by_id_cache_key(agent_id), load_agent, ttl=self.cache_ttl
        )
        if cached_agent is None:
            raise ValueError(f'Agent not found with ID: {agent_id}')
        agent_dict = json.loads(cached_agent)

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
        yaml_key = get_agent_yaml_key(
            agent_dict['namespace'], agent_dict['name'], resolved_version
        )

        async def load_yaml() -> str:
            try:
                yaml_bytes = await run_in_pool(
                    'storage',
                    self.cloud_storage_manager.read_file,
                    self.bucket_name,
                    yaml_key,
                )
            except CloudStorageFileNotFoundError:
                logger.error(
                    f'YAML not found in cloud storage for agent ID: {agent_id}, version: {resolved_version}'
                )
                raise ValueError(
                    f'Agent YAML not found for agent ID: {agent_id}, version: {resolved_version}'
                )
            return yaml_bytes.decode('utf-8')

        yaml_content = await self.cache_manager.read_through(
            get_agent_yaml_cache_key(
                agent_dict['namespace'], agent_dict['name'], resolved_version
            ),
            load_yaml,
            ttl=self.cache_ttl,
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

        async def load() -> Optional[str]:
            agent = await self.agent_repository.find_one(
                name=agent_name, namespace=namespace
            )
            return str(agent.current_version) if agent else None

        cached_version = await self.cache_manager.read_through(
            get_agent_current_version_cache_key(namespace, agent_name),
            load,
            ttl=self.current_version_cache_ttl,
        )
        if cached_version is None:
            raise ValueError(f'Agent not found: {namespace}/{agent_name}')
        return int(cached_version)

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

        yaml_key = get_agent_yaml_key(namespace, agent_name, resolved_version)

        async def load_yaml() -> str:
            try:
                yaml_bytes = await run_in_pool(
                    'storage',
                    self.cloud_storage_manager.read_file,
                    self.bucket_name,
                    yaml_key,
                )
            except CloudStorageFileNotFoundError:
                logger.error(
                    f'YAML not found in cloud storage for agent: {namespace}/{agent_name}, version: {resolved_version}'
                )
                raise ValueError(
                    f'Agent YAML not found for agent: {namespace}/{agent_name}, version: {resolved_version}'
                )
            return yaml_bytes.decode('utf-8')

        yaml_content = await self.cache_manager.read_through(
            get_agent_yaml_cache_key(namespace, agent_name, resolved_version),
            load_yaml,
            ttl=self.cache_ttl,
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

        # Strict invalidation around the write: with Redis down this fails (503)
        # before storage changes, and a read racing the edit can never put the
        # old YAML back for this version. When branching, the new version row
        # already exists, so it is rolled back on ANY failure before the upload
        # lands: the strict pre-invalidation, a refused or failed upload, or a
        # cancelled request. An in-place edit has no new row to remove.
        uploaded = False
        try:
            async with self.cache_manager.invalidating(
                get_agent_yaml_cache_key(agent.namespace, agent.name, write_version),
                get_agents_list_cache_key(None),
                get_agents_list_cache_key(agent.namespace),
            ):
                yaml_key = get_agent_yaml_key(
                    agent.namespace, agent.name, write_version
                )
                await run_in_pool(
                    'storage',
                    self.cloud_storage_manager.save_small_file,
                    file_content=yaml_content.encode('utf-8'),
                    bucket_name=self.bucket_name,
                    key=yaml_key,
                    disable_cache=True,
                )
                uploaded = True
        except BaseException:
            # Roll back, then re-raise: a busy pool or Redis outage still answers 503.
            if create_new_version and not uploaded:
                logger.error(
                    f'Failed to write YAML for new version {write_version} of agent {agent_id} - rolling back the new version row'
                )
                await self.agent_version_repository.delete_all(
                    agent_id=agent.id, version=write_version
                )
            raise

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

        cache_keys = [
            get_agent_by_id_cache_key(agent_id),
            get_agent_current_version_cache_key(agent.namespace, agent.name),
            get_agents_list_cache_key(None),
            get_agents_list_cache_key(agent.namespace),
        ] + [
            get_agent_yaml_cache_key(agent.namespace, agent.name, v.version)
            for v in versions
        ]
        async with self.cache_manager.invalidating(*cache_keys):
            # Delete from DB (cascades to agent_versions)
            await self.agent_repository.delete_all(id=agent_id)

            async def _delete_version_yaml(version: int) -> None:
                yaml_key = get_agent_yaml_key(agent.namespace, agent.name, version)
                try:
                    await asyncio.to_thread(
                        self.cloud_storage_manager.delete_file,
                        self.bucket_name,
                        yaml_key,
                    )
                except Exception as e:
                    logger.error(f'Failed to delete YAML from cloud storage: {str(e)}')
                    # Continue - DB record is deleted

            await asyncio.gather(*(_delete_version_yaml(v.version) for v in versions))

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

        async def load() -> str:
            if namespace:
                agents = await self.agent_repository.find(namespace=namespace)
            else:
                agents = await self.agent_repository.find()
            return json.dumps([agent.to_dict() for agent in agents])

        agents_list = json.loads(
            await self.cache_manager.read_through(
                get_agents_list_cache_key(namespace),
                load,
                ttl=1800,  # 30 min
            )
        )

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

        # Strict: default reads resolve current_version through these keys, so
        # an acknowledged promotion must be visible to them.
        async with self.cache_manager.invalidating(
            get_agent_by_id_cache_key(agent_id),
            get_agent_current_version_cache_key(agent.namespace, agent.name),
            get_agents_list_cache_key(None),
            get_agents_list_cache_key(agent.namespace),
        ):
            updated_agent = await self.agent_repository.find_one_and_update(
                {'id': agent_id}, current_version=version, refresh=True
            )

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

        async with self.cache_manager.invalidating(
            get_agent_yaml_cache_key(agent.namespace, agent.name, version)
        ):
            await self.agent_version_repository.find_one_and_update(
                {'agent_id': agent.id, 'version': version}, is_deleted=True
            )

        logger.info(f'Successfully deleted agent {agent_id} version {version}')
        return True
