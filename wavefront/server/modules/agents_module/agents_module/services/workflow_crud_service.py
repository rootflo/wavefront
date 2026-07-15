import asyncio
import json
import yaml
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.models.workflow import Workflow
from db_repo_module.models.workflow_version import WorkflowVersion
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from flo_cloud.cloud_storage import CloudStorageManager
from flo_cloud.exceptions import CloudStorageFileNotFoundError
from common_module.log.logger import logger
from agents_module.services.namespace_service import NamespaceService
from agents_module.utils.workflow_utils import get_workflow_yaml_key
from agents_module.utils.cache_utils import (
    get_workflow_by_id_cache_key,
    get_workflow_current_version_cache_key,
    get_workflow_yaml_cache_key,
    get_workflows_list_cache_key,
)
from agents_module.utils.validation_utils import validate_agent_workflow_name
from agents_module.utils.version_reference_utils import (
    parse_versioned_reference,
    resolve_entity_current_version,
)
from flo_ai import AriumBuilder, AgentBuilder, Agent
from agents_module.services.agent_crud_service import AgentCrudService
from tools_module.registry.tool_loader import ToolLoader
from tools_module.registry.function_node_registry import FUNCTION_NODE_REGISTRY


class WorkflowCrudService:
    """Service for handling workflow CRUD operations with DB + cloud storage"""

    def __init__(
        self,
        workflow_repository: SQLAlchemyRepository[Workflow],
        workflow_version_repository: SQLAlchemyRepository[WorkflowVersion],
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
            workflow_version_repository: WorkflowVersion repository for per-version DB operations
            namespace_service: Namespace service for namespace operations
            cloud_storage_manager: Cloud storage manager instance
            cache_manager: Cache manager instance
            bucket_name: Name of the bucket containing workflow YAML files
            agent_crud_service: Agent CRUD service for fetching agent YAMLs
            tool_loader: Tool loader for loading agent tools
        """
        self.workflow_repository = workflow_repository
        self.workflow_version_repository = workflow_version_repository
        self.namespace_service = namespace_service
        self.cloud_storage_manager = cloud_storage_manager
        self.cache_manager = cache_manager
        self.bucket_name = bucket_name
        self.agent_crud_service = agent_crud_service
        self.tool_loader = tool_loader
        self.cache_ttl = 3600  # 1 hour for workflows
        self.current_version_cache_ttl = (
            60  # short TTL for name-based version resolution
        )

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

    def _extract_subworkflow_references(self, yaml_content: str) -> List[str]:
        """
        Extract subworkflow references (namespace/workflow_name) from workflow YAML

        Args:
            yaml_content: YAML configuration content

        Returns:
            List of subworkflow references in format 'namespace/workflow_name'
        """
        try:
            yaml_data = yaml.safe_load(yaml_content)
            arium_config = yaml_data.get('arium', {})
            ariums_config = arium_config.get('ariums', [])

            subworkflow_references = []
            for arium_def in ariums_config:
                arium_name = arium_def.get('name', '')
                # If arium name contains '/', it's a reference to cloud storage
                if '/' in arium_name:
                    # Check if this is a reference (not an inline definition)
                    # If it has agents, workflow, etc., it's inline, not a reference
                    if (
                        arium_def.get('agents') is None
                        and arium_def.get('workflow') is None
                        and arium_def.get('function_nodes') is None
                        and arium_def.get('yaml_file') is None
                    ):
                        subworkflow_references.append(arium_name)
                        logger.info(f'Found subworkflow reference: {arium_name}')

            return subworkflow_references
        except Exception as e:
            logger.error(f'Error extracting subworkflow references from YAML: {str(e)}')
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
                agent_name, version = parse_versioned_reference(parts[1])

                logger.info(
                    f'Fetching and building agent for validation: namespace={namespace}, agent_name={agent_name}, version={version}'
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
        )

    async def get_workflow_yaml_from_bucket(
        self, workflow_name: str, namespace: str, version: Optional[int] = None
    ) -> str:
        """
        Get workflow YAML content by name and namespace (for workflow references)

        This method is used to fetch subworkflow YAML when they
        have namespace/workflow_name references

        Args:
            workflow_name: The workflow name
            namespace: The namespace name
            version: Specific version to fetch; defaults to the workflow's current_version

        Returns:
            str: The YAML content as string

        Raises:
            ValueError: If workflow not found
        """
        resolved_version = version
        if resolved_version is None:
            resolved_version = await self._resolve_workflow_current_version(
                workflow_name, namespace
            )
        else:
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

        # Try YAML cache first
        yaml_cache_key = get_workflow_yaml_cache_key(
            namespace, workflow_name, resolved_version
        )
        cached_yaml = self.cache_manager.get_str(yaml_cache_key)

        if cached_yaml:
            logger.info(
                f'Cache hit for workflow YAML - namespace: {namespace}, name: {workflow_name}, version: {resolved_version}'
            )
            return cached_yaml

        # Fetch YAML from cloud storage
        yaml_key = get_workflow_yaml_key(namespace, workflow_name, resolved_version)
        logger.info(f'Fetching workflow YAML from storage - key: {yaml_key}')

        try:
            yaml_bytes = self.cloud_storage_manager.read_file(
                self.bucket_name, yaml_key
            )
            yaml_content = yaml_bytes.decode('utf-8')

            # Cache YAML
            self.cache_manager.add(yaml_cache_key, yaml_content, expiry=self.cache_ttl)
        except CloudStorageFileNotFoundError:
            logger.error(
                f'YAML not found in cloud storage for workflow: {namespace}/{workflow_name}, version: {resolved_version}'
            )
            raise ValueError(
                f'Workflow YAML not found for workflow: {namespace}/{workflow_name}, version: {resolved_version}'
            )

        logger.info(
            f'Successfully retrieved workflow YAML - namespace: {namespace}, name: {workflow_name}, version: {resolved_version}'
        )
        return yaml_content

    async def _inline_subworkflow_references(
        self,
        yaml_content: str,
        subworkflow_references: List[str],
    ) -> str:
        """
        Fetch subworkflow YAML and inline them into the parent workflow YAML

        Args:
            yaml_content: Original YAML configuration content
            subworkflow_references: List of subworkflow references to inline

        Returns:
            Modified YAML content with inlined subworkflow definitions
        """
        if not subworkflow_references:
            return yaml_content

        yaml_data = yaml.safe_load(yaml_content)
        arium_config = yaml_data.get('arium', {})
        ariums_config = arium_config.get('ariums', [])

        # Build a dict to quickly look up subworkflow configs
        subworkflow_configs = {}
        for ref in subworkflow_references:
            parts = ref.split('/', 1)
            namespace = parts[0]
            workflow_name, version = parse_versioned_reference(parts[1])

            logger.info(f'Fetching subworkflow YAML for inlining: {ref}')

            # Fetch the subworkflow YAML
            subworkflow_yaml_content = await self.get_workflow_yaml_from_bucket(
                workflow_name, namespace, version=version
            )

            # Parse and extract the arium config
            subworkflow_data = yaml.safe_load(subworkflow_yaml_content)
            subworkflow_arium = subworkflow_data.get('arium', {})

            subworkflow_configs[ref] = subworkflow_arium

        # Replace references with inline definitions
        updated_ariums = []
        for arium_def in ariums_config:
            arium_name = arium_def.get('name', '')

            if arium_name in subworkflow_configs:
                # This is a reference - inline it
                logger.info(f'Inlining subworkflow: {arium_name}')

                # Get the fetched subworkflow config
                inline_config = subworkflow_configs[arium_name].copy()

                # Preserve inherit_variables from the reference
                if 'inherit_variables' in arium_def:
                    inline_config['inherit_variables'] = arium_def['inherit_variables']

                # Update the name to be local (remove namespace prefix and any @version)
                local_name, _ = parse_versioned_reference(arium_name.split('/')[-1])
                inline_config['name'] = local_name

                updated_ariums.append(inline_config)
            else:
                # Not a reference - keep as is
                updated_ariums.append(arium_def)

        # Update the YAML data
        yaml_data['arium']['ariums'] = updated_ariums

        # Convert back to YAML string
        return yaml.dump(yaml_data, default_flow_style=False, sort_keys=False)

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
            # Extract and inline subworkflow references
            subworkflow_references = self._extract_subworkflow_references(yaml_content)
            if subworkflow_references:
                logger.info(
                    f'Inlining {len(subworkflow_references)} referenced subworkflows for validation'
                )
                yaml_content = await self._inline_subworkflow_references(
                    yaml_content, subworkflow_references
                )

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

            # Validate workflow with pre-built agents and inlined subworkflows
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

        # Create workflow identity row, then its first version row. These are two
        # separate, non-atomic calls; if the second one fails, compensate by
        # removing the identity row rather than leaving an orphaned workflow with
        # zero versions that would permanently block this (name, namespace) pair.
        workflow = await self.workflow_repository.create(
            name=name, namespace=namespace_dict['name'], current_version=1
        )
        try:
            await self.workflow_version_repository.create(
                workflow_id=workflow.id, version=1, is_deleted=False
            )
        except Exception:
            logger.error(
                f'Failed to create first version for workflow {workflow.id} - rolling back identity row'
            )
            await self.workflow_repository.delete_all(id=workflow.id)
            raise

        # Upload YAML to cloud storage
        yaml_key = get_workflow_yaml_key(namespace, name, 1)
        yaml_bytes = yaml_content.encode('utf-8')
        self.cloud_storage_manager.save_small_file(
            file_content=yaml_bytes,
            bucket_name=self.bucket_name,
            key=yaml_key,
            disable_cache=True,
        )

        # Build response with YAML content
        workflow_dict = workflow.to_dict()
        workflow_dict['version'] = 1
        workflow_dict['yaml_content'] = yaml_content

        # Cache workflow metadata
        workflow_cache_key = get_workflow_by_id_cache_key(workflow.id)
        self.cache_manager.add(
            workflow_cache_key, json.dumps(workflow.to_dict()), expiry=self.cache_ttl
        )

        # Cache YAML content
        yaml_cache_key = get_workflow_yaml_cache_key(namespace, name, 1)
        self.cache_manager.add(yaml_cache_key, yaml_content, expiry=self.cache_ttl)

        # Invalidate list caches
        self.cache_manager.remove(get_workflows_list_cache_key(None))
        self.cache_manager.remove(get_workflows_list_cache_key(namespace))

        logger.info(
            f'Successfully created workflow - namespace: {namespace}, name: {name}'
        )
        return workflow_dict

    async def get_workflow(
        self, workflow_id: UUID, version: Optional[int] = None
    ) -> dict:
        """
        Get workflow by ID with YAML content

        Args:
            workflow_id: The workflow UUID
            version: Specific version to fetch; defaults to the workflow's current_version

        Returns:
            dict: Workflow details including YAML content, with 'version' set to
                whichever version was actually resolved

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

        resolved_version = (
            version if version is not None else workflow_dict['current_version']
        )

        if version is not None:
            version_row = await self.workflow_version_repository.find_one(
                workflow_id=workflow_id, version=version
            )
            if not version_row or version_row.is_deleted:
                raise ValueError(
                    f'Workflow YAML not found for workflow ID: {workflow_id}, version: {version}'
                )

        # Fetch YAML from cloud storage (with caching)
        yaml_cache_key = get_workflow_yaml_cache_key(
            workflow_dict['namespace'], workflow_dict['name'], resolved_version
        )
        cached_yaml = self.cache_manager.get_str(yaml_cache_key)

        if cached_yaml:
            logger.info(
                f'Cache hit for workflow YAML - namespace: {workflow_dict["namespace"]}, name: {workflow_dict["name"]}, version: {resolved_version}'
            )
            yaml_content = cached_yaml
        else:
            # Fetch YAML from cloud storage
            yaml_key = get_workflow_yaml_key(
                workflow_dict['namespace'], workflow_dict['name'], resolved_version
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
                    f'YAML not found in cloud storage for workflow ID: {workflow_id}, version: {resolved_version}'
                )
                raise ValueError(
                    f'Workflow YAML not found for workflow ID: {workflow_id}, version: {resolved_version}'
                )

        # Add version/YAML to response
        workflow_dict['version'] = resolved_version
        workflow_dict['yaml_content'] = yaml_content

        logger.info(
            f'Successfully retrieved workflow - ID: {workflow_id}, version: {resolved_version}'
        )
        return workflow_dict

    async def update_workflow(
        self,
        workflow_id: UUID,
        yaml_content: str,
        access_token: Optional[str] = None,
        app_key: Optional[str] = None,
        version: Optional[int] = None,
        create_new_version: bool = False,
    ) -> dict:
        """
        Update a workflow's YAML configuration - either in place, or as a new version

        Args:
            workflow_id: The workflow UUID
            yaml_content: Updated YAML configuration content
            version: Which existing version to edit in place, or branch a new version
                from; defaults to the workflow's current_version
            create_new_version: If True, create a new version instead of editing
                `version` in place. The new version never becomes current_version
                automatically - it must be explicitly promoted.

        Returns:
            dict: Updated workflow details, with 'version' set to whichever version
                was actually written

        Raises:
            ValueError: If workflow (or the target version) not found, or validation fails
        """
        logger.info(
            f'Updating workflow - ID: {workflow_id}, version: {version}, create_new_version: {create_new_version}'
        )

        # Fetch workflow from DB
        workflow = await self.workflow_repository.find_one(id=workflow_id)
        if not workflow:
            raise ValueError(f'Workflow not found with ID: {workflow_id}')

        target_version = version if version is not None else workflow.current_version

        # Validate YAML content
        await self._validate_yaml_content(
            yaml_content, workflow.namespace, workflow.name, access_token, app_key
        )

        if create_new_version:
            existing_versions = await self.workflow_version_repository.find(
                workflow_id=workflow.id, limit=100000
            )
            source_version = next(
                (v for v in existing_versions if v.version == target_version), None
            )
            if not source_version or source_version.is_deleted:
                raise ValueError(
                    f'Workflow {workflow_id} has no version {target_version} to branch from'
                )
            write_version = max(v.version for v in existing_versions) + 1
            try:
                await self.workflow_version_repository.create(
                    workflow_id=workflow.id, version=write_version, is_deleted=False
                )
            except IntegrityError:
                # Another concurrent create_new_version call already took write_version.
                raise ValueError(
                    f'Concurrent version creation conflict for workflow {workflow_id} - please retry'
                )
        else:
            existing_version = await self.workflow_version_repository.find_one(
                workflow_id=workflow.id, version=target_version
            )
            if not existing_version or existing_version.is_deleted:
                raise ValueError(
                    f'Workflow {workflow_id} has no version {target_version} to update'
                )
            write_version = target_version

        # Write YAML to cloud storage at the resolved version's key
        yaml_key = get_workflow_yaml_key(
            workflow.namespace, workflow.name, write_version
        )
        yaml_bytes = yaml_content.encode('utf-8')
        self.cloud_storage_manager.save_small_file(
            file_content=yaml_bytes,
            bucket_name=self.bucket_name,
            key=yaml_key,
            disable_cache=True,
        )

        # Invalidate caches
        yaml_cache_key = get_workflow_yaml_cache_key(
            workflow.namespace, workflow.name, write_version
        )
        self.cache_manager.remove(yaml_cache_key)

        # Invalidate list caches
        self.cache_manager.remove(get_workflows_list_cache_key(None))
        self.cache_manager.remove(get_workflows_list_cache_key(workflow.namespace))

        # Build response
        workflow_dict = workflow.to_dict()
        workflow_dict['version'] = write_version
        workflow_dict['yaml_content'] = yaml_content

        logger.info(
            f'Successfully updated workflow - ID: {workflow_id}, version: {write_version}'
        )
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

        # Fetch every version so we can clean up storage/caches for each of them
        # before the identity row (and, via FK cascade, the version rows) are deleted.
        versions = await self.workflow_version_repository.find(
            workflow_id=workflow.id, limit=100000
        )

        # Delete from DB (cascades to workflow_versions)
        await self.workflow_repository.delete_all(id=workflow_id)

        async def _delete_version_yaml(version: int) -> None:
            yaml_key = get_workflow_yaml_key(workflow.namespace, workflow.name, version)
            try:
                await asyncio.to_thread(
                    self.cloud_storage_manager.delete_file, self.bucket_name, yaml_key
                )
            except Exception as e:
                logger.error(f'Failed to delete YAML from cloud storage: {str(e)}')
                # Continue - DB record is deleted

            yaml_cache_key = get_workflow_yaml_cache_key(
                workflow.namespace, workflow.name, version
            )
            self.cache_manager.remove(yaml_cache_key)

        await asyncio.gather(*(_delete_version_yaml(v.version) for v in versions))

        # Invalidate caches
        workflow_cache_key = get_workflow_by_id_cache_key(workflow_id)
        self.cache_manager.remove(workflow_cache_key)
        self.cache_manager.remove(
            get_workflow_current_version_cache_key(workflow.namespace, workflow.name)
        )

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

    async def promote_workflow_version(self, workflow_id: UUID, version: int) -> dict:
        """
        Make an existing version the workflow's current_version

        Args:
            workflow_id: The workflow UUID
            version: The version to promote

        Returns:
            dict: Updated workflow details

        Raises:
            ValueError: If workflow not found, or the version doesn't exist / is deleted
        """
        logger.info(f'Promoting workflow {workflow_id} to version {version}')

        workflow = await self.workflow_repository.find_one(id=workflow_id)
        if not workflow:
            raise ValueError(f'Workflow not found with ID: {workflow_id}')

        target_version = await self.workflow_version_repository.find_one(
            workflow_id=workflow.id, version=version
        )
        if not target_version or target_version.is_deleted:
            raise ValueError(
                f'Workflow {workflow_id} has no live version {version} to promote'
            )

        updated_workflow = await self.workflow_repository.find_one_and_update(
            {'id': workflow_id}, current_version=version, refresh=True
        )

        self.cache_manager.remove(get_workflow_by_id_cache_key(workflow_id))
        self.cache_manager.remove(
            get_workflow_current_version_cache_key(workflow.namespace, workflow.name)
        )
        self.cache_manager.remove(get_workflows_list_cache_key(None))
        self.cache_manager.remove(get_workflows_list_cache_key(workflow.namespace))

        logger.info(
            f'Successfully promoted workflow {workflow_id} to version {version}'
        )
        return updated_workflow.to_dict()

    async def list_workflow_versions(self, workflow_id: UUID) -> List[dict]:
        """
        List every live (non-deleted) version of a workflow

        Args:
            workflow_id: The workflow UUID

        Returns:
            List[dict]: Versions sorted ascending, each annotated with 'is_current'

        Raises:
            ValueError: If workflow not found
        """
        workflow = await self.workflow_repository.find_one(id=workflow_id)
        if not workflow:
            raise ValueError(f'Workflow not found with ID: {workflow_id}')

        versions = await self.workflow_version_repository.find(
            workflow_id=workflow.id, limit=100000
        )

        version_dicts = []
        for workflow_version in sorted(versions, key=lambda v: v.version):
            if workflow_version.is_deleted:
                continue
            version_dict = workflow_version.to_dict()
            version_dict['is_current'] = (
                workflow_version.version == workflow.current_version
            )
            version_dicts.append(version_dict)

        return version_dicts

    async def delete_workflow_version(self, workflow_id: UUID, version: int) -> bool:
        """
        Soft-delete a single version of a workflow

        The current_version is never left dangling: deleting the version that is
        currently current_version is rejected until a different version is
        promoted first. Version numbers are never reused.

        Args:
            workflow_id: The workflow UUID
            version: The version to delete

        Returns:
            bool: Success status

        Raises:
            ValueError: If workflow/version not found, or version is the current_version
        """
        logger.info(f'Deleting workflow {workflow_id} version {version}')

        workflow = await self.workflow_repository.find_one(id=workflow_id)
        if not workflow:
            raise ValueError(f'Workflow not found with ID: {workflow_id}')

        if version == workflow.current_version:
            raise ValueError(
                f'Cannot delete version {version} of workflow {workflow_id} because it is '
                'the current version - promote a different version first'
            )

        target_version = await self.workflow_version_repository.find_one(
            workflow_id=workflow.id, version=version
        )
        if not target_version or target_version.is_deleted:
            raise ValueError(
                f'Workflow {workflow_id} has no live version {version} to delete'
            )

        await self.workflow_version_repository.find_one_and_update(
            {'workflow_id': workflow.id, 'version': version}, is_deleted=True
        )

        self.cache_manager.remove(
            get_workflow_yaml_cache_key(workflow.namespace, workflow.name, version)
        )

        logger.info(f'Successfully deleted workflow {workflow_id} version {version}')
        return True
