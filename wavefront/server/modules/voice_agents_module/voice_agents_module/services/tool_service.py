import json
import uuid
from typing import List, Optional, Dict, Any
from uuid import UUID

from common_module.log.logger import logger
from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.models.voice_agent_tool import VoiceAgentTool
from db_repo_module.models.voice_agent_tool_association import VoiceAgentToolAssociation
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from voice_agents_module.models.tool_schemas import (
    CreateToolPayload,
    UpdateToolPayload,
    AttachToolToAgentPayload,
    UpdateAgentToolPayload,
    ToolType,
    ApiToolConfig,
    PythonToolConfig,
    UNSET,
)
from voice_agents_module.utils.cache_invalidation import (
    invalidate_call_processing_cache,
)


class ToolService:
    """Service for handling tool CRUD operations with caching"""

    def __init__(
        self,
        tool_repository: SQLAlchemyRepository[VoiceAgentTool],
        tool_association_repository: SQLAlchemyRepository[VoiceAgentToolAssociation],
        cache_manager: CacheManager,
    ):
        """
        Initialize the tool service

        Args:
            tool_repository: Repository for voice agent tools
            tool_association_repository: Repository for voice agent tool associations
            cache_manager: Cache manager instance
        """
        self.tool_repository = tool_repository
        self.tool_association_repository = tool_association_repository
        self.cache_manager = cache_manager
        self.tool_cache_time = 3600 * 24  # 24 hours matching voice agent pattern

    def _get_tool_cache_key(self, tool_id: UUID) -> str:
        """Generate cache key for a single tool"""
        return f'tool:{tool_id}'

    def _get_tools_list_cache_key(self) -> str:
        """Generate cache key for tools list"""
        return 'tools:list'

    def _get_agent_tools_cache_key(self, agent_id: UUID) -> str:
        """Generate cache key for agent's tools"""
        return f'voice_agent:{agent_id}:tools'

    async def create_tool(self, payload: CreateToolPayload) -> VoiceAgentTool:
        """
        Create a new tool

        Args:
            payload: Tool creation payload

        Returns:
            Created VoiceAgentTool instance

        Raises:
            ValueError: If tool with same name exists
        """
        try:
            # Check if tool with same name exists
            existing = await self.tool_repository.find_one(name=payload.name)
            if existing:
                raise ValueError(f'Tool with name "{payload.name}" already exists')

            # Get tool_type as string and ensure lowercase
            tool_type_str = (
                payload.tool_type
                if isinstance(payload.tool_type, str)
                else payload.tool_type.value
            )
            tool_type_str = tool_type_str.lower()  # Ensure lowercase for database enum

            # Save to database
            created_tool = await self.tool_repository.create(
                id=uuid.uuid4(),
                name=payload.name,
                display_name=payload.display_name,
                description=payload.description,
                tool_type=tool_type_str,  # Pass string directly, SQLAlchemy handles enum conversion
                config=payload.config,
                parameter_schema=payload.parameter_schema,
                response_template=payload.response_template,
                created_by=payload.created_by,
            )

            # Invalidate list cache
            self.cache_manager.remove(self._get_tools_list_cache_key())

            logger.info(f'Created tool: {created_tool.name} (ID: {created_tool.id})')
            return created_tool

        except Exception as e:
            logger.error(f'Error creating tool: {str(e)}')
            raise

    async def get_tool(
        self, tool_id: UUID, exclude_sensitive: bool = True
    ) -> Optional[VoiceAgentTool]:
        """
        Get a tool by ID with caching

        Args:
            tool_id: Tool ID
            exclude_sensitive: Whether to mask sensitive data in config

        Returns:
            VoiceAgentTool instance or None
        """
        try:
            cache_key = self._get_tool_cache_key(tool_id)

            # Try to get from cache
            cached_str = self.cache_manager.get_str(cache_key)
            if cached_str:
                logger.debug(f'Tool {tool_id} retrieved from cache')
                # Reconstruct tool from cached dict
                cached_data = json.loads(cached_str)
                tool = VoiceAgentTool(**cached_data)
                return tool

            # Get from database
            tool = await self.tool_repository.find_one(id=tool_id, is_deleted=False)

            if tool:
                # Cache the tool data
                tool_dict = tool.to_dict(exclude_sensitive=False)  # Cache unmasked
                self.cache_manager.add(
                    cache_key, json.dumps(tool_dict), expiry=self.tool_cache_time
                )
                logger.debug(f'Tool {tool_id} cached for {self.tool_cache_time}s')

            return tool

        except Exception as e:
            logger.error(f'Error getting tool {tool_id}: {str(e)}')
            raise

    async def list_tools(
        self, include_deleted: bool = False, tool_type: Optional[str] = None
    ) -> List[VoiceAgentTool]:
        """
        List all tools with caching

        Args:
            include_deleted: Whether to include soft-deleted tools
            tool_type: Filter by tool type (api, python)

        Returns:
            List of VoiceAgentTool instances
        """
        try:
            cache_key = self._get_tools_list_cache_key()

            # Try to get from cache (only for non-deleted, all types)
            if not include_deleted and tool_type is None:
                cached_str = self.cache_manager.get_str(cache_key)
                if cached_str:
                    logger.debug('Tools list retrieved from cache')
                    # Reconstruct tools from cached list
                    cached_data = json.loads(cached_str)
                    tools = [VoiceAgentTool(**tool_dict) for tool_dict in cached_data]
                    return tools

            # Build filters
            filters = {}
            if not include_deleted:
                filters['is_deleted'] = False
            if tool_type:
                filters['tool_type'] = tool_type  # Pass string value directly

            # Get from database
            tools = await self.tool_repository.find(limit=1000, **filters)

            # Cache if appropriate
            if not include_deleted and tool_type is None:
                tools_data = [tool.to_dict(exclude_sensitive=False) for tool in tools]
                self.cache_manager.add(
                    cache_key, json.dumps(tools_data), expiry=self.tool_cache_time
                )
                logger.debug(f'Tools list cached for {self.tool_cache_time}s')

            return tools

        except Exception as e:
            logger.error(f'Error listing tools: {str(e)}')
            raise

    async def update_tool(
        self, tool_id: UUID, payload: UpdateToolPayload
    ) -> VoiceAgentTool:
        """
        Update a tool

        Args:
            tool_id: Tool ID
            payload: Update payload with optional fields

        Returns:
            Updated VoiceAgentTool instance

        Raises:
            ValueError: If tool not found or name conflict
        """
        try:
            # Get existing tool
            tool = await self.tool_repository.find_one(id=tool_id, is_deleted=False)
            if not tool:
                raise ValueError(f'Tool with ID {tool_id} not found')

            # Prepare update data
            update_data = {}
            for field, value in payload.model_dump().items():
                if value is not UNSET:
                    update_data[field] = value

            # Validate and normalize tool_type if provided
            if 'tool_type' in update_data:
                tool_type_value = update_data['tool_type']
                # Convert enum to string value if needed
                if hasattr(tool_type_value, 'value'):
                    tool_type_value = tool_type_value.value
                tool_type_value = str(tool_type_value).lower()
                # Validate against ToolType enum
                valid_types = {t.value for t in ToolType}
                if tool_type_value not in valid_types:
                    raise ValueError(
                        f'Invalid tool_type: {tool_type_value}. Must be one of {valid_types}'
                    )
                update_data['tool_type'] = tool_type_value

            # Validate config against the appropriate schema
            if 'config' in update_data and isinstance(update_data['config'], dict):
                tool_type_value = update_data.get('tool_type')
                if not tool_type_value:
                    tool_type_value = tool.tool_type
                tool_type_value = (
                    tool_type_value.value
                    if hasattr(tool_type_value, 'value')
                    else str(tool_type_value).lower()
                )
                try:
                    if tool_type_value == 'api':
                        ApiToolConfig(**update_data['config'])
                    elif tool_type_value == 'python':
                        PythonToolConfig(**update_data['config'])
                except Exception as e:
                    raise ValueError(
                        f'Invalid config for tool type {tool_type_value}: {str(e)}'
                    )

            # Handle credentials in config updates
            if 'config' in update_data and isinstance(update_data['config'], dict):
                existing_config = tool.config or {}
                auth_creds = update_data['config'].get('auth_credentials')

                if auth_creds == {'masked': True}:
                    # Explicit masked indicator - preserve existing credentials
                    logger.info(
                        f'Preserving existing credentials for tool {tool_id} (masked indicator)'
                    )
                    if 'auth_credentials' in existing_config:
                        update_data['config']['auth_credentials'] = existing_config[
                            'auth_credentials'
                        ]
                    else:
                        # No existing credentials, remove masked placeholder
                        del update_data['config']['auth_credentials']
                elif 'auth_credentials' not in update_data['config']:
                    # auth_credentials not included in update - preserve existing
                    logger.info(
                        f'Preserving existing credentials for tool {tool_id} (not in update)'
                    )
                    if 'auth_credentials' in existing_config:
                        update_data['config']['auth_credentials'] = existing_config[
                            'auth_credentials'
                        ]
                # else: new credentials provided, use them

            # Check name uniqueness if name is being updated
            if 'name' in update_data and update_data['name'] != tool.name:
                existing = await self.tool_repository.find_one(
                    name=update_data['name'], is_deleted=False
                )
                if existing:
                    raise ValueError(
                        f'Tool with name "{update_data["name"]}" already exists'
                    )

            # Update tool
            updated_tool = await self.tool_repository.find_one_and_update(
                filters={'id': tool_id}, refresh=True, **update_data
            )

            # Invalidate caches
            self.cache_manager.remove(self._get_tool_cache_key(tool_id))
            self.cache_manager.remove(self._get_tools_list_cache_key())

            # Invalidate agent tools cache for all agents using this tool
            associations = await self.tool_association_repository.find(
                limit=1000, tool_id=tool_id
            )
            for assoc in associations:
                self.cache_manager.remove(
                    self._get_agent_tools_cache_key(assoc.voice_agent_id)
                )
                # Invalidate call processing cache
                await invalidate_call_processing_cache(
                    'voice_agent', assoc.voice_agent_id, 'update'
                )

            logger.info(f'Updated tool: {updated_tool.name} (ID: {tool_id})')
            return updated_tool

        except Exception as e:
            logger.error(f'Error updating tool {tool_id}: {str(e)}')
            raise

    async def delete_tool(self, tool_id: UUID) -> bool:
        """
        Soft delete a tool

        Args:
            tool_id: Tool ID

        Returns:
            True if successful

        Raises:
            ValueError: If tool not found
        """
        try:
            # Get existing tool
            tool = await self.tool_repository.find_one(id=tool_id, is_deleted=False)
            if not tool:
                raise ValueError(f'Tool with ID {tool_id} not found')

            # Soft delete
            await self.tool_repository.find_one_and_update(
                filters={'id': tool_id}, refresh=True, is_deleted=True
            )

            # Delete all associations for this tool
            associations = await self.tool_association_repository.find(
                limit=1000, tool_id=tool_id
            )
            for assoc in associations:
                await self.tool_association_repository.delete_all(id=assoc.id)
                # Invalidate agent cache
                self.cache_manager.remove(
                    self._get_agent_tools_cache_key(assoc.voice_agent_id)
                )
                # Invalidate call processing cache
                await invalidate_call_processing_cache(
                    'voice_agent', assoc.voice_agent_id, 'update'
                )

            # Invalidate caches
            self.cache_manager.remove(self._get_tool_cache_key(tool_id))
            self.cache_manager.remove(self._get_tools_list_cache_key())

            logger.info(f'Deleted tool: {tool.name} (ID: {tool_id})')
            return True

        except Exception as e:
            logger.error(f'Error deleting tool {tool_id}: {str(e)}')
            raise

    async def attach_tool_to_agent(
        self, agent_id: UUID, payload: AttachToolToAgentPayload
    ) -> VoiceAgentToolAssociation:
        """
        Attach a tool to a voice agent

        Args:
            agent_id: Voice agent ID
            payload: Attachment payload

        Returns:
            Created association

        Raises:
            ValueError: If tool not found or already attached
        """
        try:
            # Check if tool exists
            tool = await self.get_tool(payload.tool_id)
            if not tool:
                raise ValueError(f'Tool with ID {payload.tool_id} not found')

            # Check if already attached
            existing = await self.tool_association_repository.find_one(
                voice_agent_id=agent_id, tool_id=payload.tool_id
            )
            if existing:
                raise ValueError(
                    f'Tool {payload.tool_id} already attached to agent {agent_id}'
                )

            # Create association
            created = await self.tool_association_repository.create(
                id=uuid.uuid4(),
                voice_agent_id=agent_id,
                tool_id=payload.tool_id,
                is_enabled=payload.is_enabled,
                config_overrides=payload.config_overrides,
                priority=payload.priority,
            )

            # Invalidate agent tools cache
            self.cache_manager.remove(self._get_agent_tools_cache_key(agent_id))
            # Invalidate call processing cache
            await invalidate_call_processing_cache('voice_agent', agent_id, 'update')

            logger.info(
                f'Attached tool {payload.tool_id} to agent {agent_id} (priority: {payload.priority})'
            )
            return created

        except Exception as e:
            logger.error(f'Error attaching tool to agent {agent_id}: {str(e)}')
            raise

    async def detach_tool_from_agent(self, agent_id: UUID, tool_id: UUID) -> bool:
        """
        Detach a tool from a voice agent

        Args:
            agent_id: Voice agent ID
            tool_id: Tool ID

        Returns:
            True if successful

        Raises:
            ValueError: If association not found
        """
        try:
            # Find association
            association = await self.tool_association_repository.find_one(
                voice_agent_id=agent_id, tool_id=tool_id
            )
            if not association:
                raise ValueError(f'Tool {tool_id} not attached to agent {agent_id}')

            # Delete association
            await self.tool_association_repository.delete_all(id=association.id)

            # Invalidate agent tools cache
            self.cache_manager.remove(self._get_agent_tools_cache_key(agent_id))
            # Invalidate call processing cache
            await invalidate_call_processing_cache('voice_agent', agent_id, 'update')

            logger.info(f'Detached tool {tool_id} from agent {agent_id}')
            return True

        except Exception as e:
            logger.error(f'Error detaching tool from agent {agent_id}: {str(e)}')
            raise

    async def get_agent_tools(self, agent_id: UUID) -> List[Dict[str, Any]]:
        """
        Get all tools for a voice agent (sorted by priority)

        Args:
            agent_id: Voice agent ID

        Returns:
            List of tool dicts with association details
        """
        try:
            cache_key = self._get_agent_tools_cache_key(agent_id)

            # Try to get from cache
            cached_str = self.cache_manager.get_str(cache_key)
            if cached_str:
                logger.debug(f'Agent {agent_id} tools retrieved from cache')
                return json.loads(cached_str)

            # Get associations sorted by priority (descending)
            # Note: SQLAlchemyRepository.find() doesn't support order_by, results may not be sorted
            associations = await self.tool_association_repository.find(
                limit=1000, voice_agent_id=agent_id
            )
            # Sort in Python since repo doesn't support order_by
            associations = sorted(associations, key=lambda x: x.priority, reverse=True)

            # Build result with tool details
            result = []
            for assoc in associations:
                tool = await self.get_tool(assoc.tool_id, exclude_sensitive=False)
                if tool and not tool.is_deleted:
                    tool_data = tool.to_dict(exclude_sensitive=False)
                    tool_data['association'] = {
                        'is_enabled': assoc.is_enabled,
                        'config_overrides': assoc.config_overrides,
                        'priority': assoc.priority,
                    }
                    result.append(tool_data)

            # Cache the result
            self.cache_manager.add(
                cache_key, json.dumps(result), expiry=self.tool_cache_time
            )
            logger.debug(
                f'Agent {agent_id} tools cached ({len(result)} tools, {self.tool_cache_time}s TTL)'
            )

            return result

        except Exception as e:
            logger.error(f'Error getting tools for agent {agent_id}: {str(e)}')
            raise

    async def update_agent_tool(
        self, agent_id: UUID, tool_id: UUID, payload: UpdateAgentToolPayload
    ) -> VoiceAgentToolAssociation:
        """
        Update a tool association for an agent

        Args:
            agent_id: Voice agent ID
            tool_id: Tool ID
            payload: Update payload

        Returns:
            Updated association

        Raises:
            ValueError: If association not found
        """
        try:
            # Find association
            association = await self.tool_association_repository.find_one(
                voice_agent_id=agent_id, tool_id=tool_id
            )
            if not association:
                raise ValueError(f'Tool {tool_id} not attached to agent {agent_id}')

            # Prepare update data
            update_data = {}
            for field, value in payload.model_dump().items():
                if value is not UNSET:
                    update_data[field] = value

            # Update association
            updated = await self.tool_association_repository.find_one_and_update(
                filters={'id': association.id}, refresh=True, **update_data
            )

            # Invalidate agent tools cache
            self.cache_manager.remove(self._get_agent_tools_cache_key(agent_id))
            # Invalidate call processing cache
            await invalidate_call_processing_cache('voice_agent', agent_id, 'update')

            logger.info(f'Updated tool {tool_id} association for agent {agent_id}')
            return updated

        except Exception as e:
            logger.error(f'Error updating agent tool association: {str(e)}')
            raise
