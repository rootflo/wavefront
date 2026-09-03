"""
Initializes all services once per worker process.
No DB connection owned by the worker — status updates go through Redis Streams.
DB credentials are read from env vars so config.ini is not required.
"""

import asyncio
import threading
from dataclasses import dataclass
from typing import Optional

from dependency_injector import providers

from api_services_module.api_services_container import (
    ApiServicesContainer,
    create_api_services_container,
)
from agents_module.agents_container import AgentsContainer
from llm_inference_config_module.container import LlmInferenceConfigContainer
from agents_module.services.agent_inference_service import AgentInferenceService
from agents_module.services.workflow_inference_service import WorkflowInferenceService
from common_module.common_container import CommonContainer
from common_module.log.logger import logger
from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.database.connection import DatabaseConfig, DatabaseClient
from db_repo_module.db_repo_container import DatabaseModuleContainer
from flo_cloud.cloud_storage import CloudStorageManager
from plugins_module.plugins_container import PluginsContainer
from tools_module.tools_container import ToolsContainer
from triggers_module.services.trigger_event_processor import TriggerEventProcessor
from triggers_module.triggers_container import TriggersContainer

from celery_worker.env import (
    AGENT_YAML_BUCKET,
    AGENTIC_EXECUTIONS_BUCKET,
    APP_NAME,
    CLOUD_PROVIDER,
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_PORT,
    DB_USERNAME,
    GCP_PROJECT_ID,
    GMAIL_PUBSUB_OIDC_SA_EMAIL,
    GMAIL_PUBSUB_TOPIC_PREFIX,
    GMAIL_PUSH_ENDPOINT_TEMPLATE,
    GOOGLE_OAUTH_CLIENT_ID,
    GOOGLE_OAUTH_CLIENT_SECRET,
    GOOGLE_OAUTH_REDIRECT_URI,
    WORKFLOW_WORKER_TOPIC,
)


@dataclass
class WorkerServices:
    agent_inference: AgentInferenceService
    workflow_inference: WorkflowInferenceService
    cloud_storage: CloudStorageManager
    cache: CacheManager
    execution_bucket: str
    trigger_event_processor: TriggerEventProcessor


_lock = threading.Lock()
_services: Optional[WorkerServices] = None

_loop_lock = threading.Lock()
_loop: Optional[asyncio.AbstractEventLoop] = None

# Per-phase ceiling on the shutdown drain, so teardown always terminates.
# Worst case is 3x this (grace, cancel-reap, asyncgens) and only occurs if a
# task ignores cancellation; the normal path finishes in milliseconds.
_LOOP_DRAIN_TIMEOUT_S = 5.0


def _drain_tasks(loop: asyncio.AbstractEventLoop, timeout: float) -> list:
    """Run pending tasks on `loop` for at most `timeout` seconds.

    Returns the tasks still unfinished. asyncio.wait() is used rather than
    gather() because it reports the timeout instead of raising, and never
    cancels on its own — phase 2 decides that explicitly.
    """
    pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
    if not pending:
        return []

    try:
        loop.run_until_complete(asyncio.wait(pending, timeout=timeout))
    except Exception as exc:
        logger.warning(f'Error draining worker event loop: {exc}')

    return [t for t in pending if not t.done()]


def get_event_loop() -> asyncio.AbstractEventLoop:
    """One event loop for the lifetime of the worker process.

    Tasks used to create and close a loop per run. Because WorkerServices is a
    process-wide singleton built during the first task, every async client it
    holds stayed bound to that first loop — so later tasks ran against clients
    owned by a closed loop, and httpx AsyncClient.aclose() finalizers raised
    'Event loop is closed'. Sharing one loop keeps those clients and their
    connection pools valid for the whole process.
    """
    global _loop
    if _loop is not None and not _loop.is_closed():
        return _loop

    with _loop_lock:
        if _loop is None or _loop.is_closed():
            _loop = asyncio.new_event_loop()
            # Set the thread default too, so library __del__ paths that call
            # get_event_loop() outside a running loop find a live one.
            asyncio.set_event_loop(_loop)

    return _loop


def close_event_loop() -> None:
    """Tear the shared loop down cleanly at worker-process shutdown."""
    global _loop
    if _loop is None or _loop.is_closed():
        return

    with _loop_lock:
        if _loop is None or _loop.is_closed():
            return
        if _loop.is_running():
            # Under the solo pool tasks run in the main thread, so a shutdown
            # signal handler can land on top of a running task. Draining or
            # closing a running loop raises, and that exception would surface
            # inside the task. Leave it to process teardown instead.
            logger.warning(
                'Worker event loop still running at shutdown; skipping close'
            )
            return
        try:
            # Phase 1: let client finalizers (aclose() and friends) finish on
            # their own — that is the whole reason this drain exists.
            stragglers = _drain_tasks(_loop, _LOOP_DRAIN_TIMEOUT_S)

            # Phase 2: cancel and reap whatever is left. Tasks now outlive the
            # run that created them, so without this a single leaked task would
            # block worker shutdown indefinitely.
            if stragglers:
                for task in stragglers:
                    task.cancel()
                stragglers = _drain_tasks(_loop, _LOOP_DRAIN_TIMEOUT_S)

            if stragglers:
                logger.warning(
                    f'{len(stragglers)} task(s) ignored cancellation on the '
                    'worker event loop; closing anyway'
                )

            _loop.run_until_complete(
                asyncio.wait_for(
                    _loop.shutdown_asyncgens(), timeout=_LOOP_DRAIN_TIMEOUT_S
                )
            )
        except Exception as exc:
            logger.warning(f'Error draining worker event loop on shutdown: {exc}')
        finally:
            # Telemetry shutdown is handled by the `worker_shutdown` /
            # `worker_process_shutdown` signals in celery_app.py, not here —
            # this function's contract is event-loop teardown, and coupling
            # span/metric flush to it meant a repeated or skipped call here
            # could lose the tail of the traces.
            _loop.close()
            _loop = None


def _build_db_client() -> DatabaseClient:
    """Build DatabaseClient directly from env vars — no config.ini needed."""
    db_config = DatabaseConfig(
        username=DB_USERNAME,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        db_name=DB_NAME,
    )
    return DatabaseClient(db_config)


def get_services() -> WorkerServices:
    global _services
    if _services is not None:
        return _services

    with _lock:
        if _services is not None:
            return _services

        # Build DB client from env vars and override the container's singleton
        db_client = _build_db_client()
        db_repo_container = DatabaseModuleContainer()
        db_repo_container.db_client.override(providers.Object(db_client))

        common_container = CommonContainer(
            cache_manager=db_repo_container.cache_manager
        )

        # Override cloud storage manager with env-var-based provider
        common_container.cloud_storage_manager.override(
            providers.Object(CloudStorageManager(provider=CLOUD_PROVIDER))
        )

        api_services_container: ApiServicesContainer = create_api_services_container(
            api_service_repository=db_repo_container.api_services_repository,
            cloud_storage_manager=common_container.cloud_storage_manager,
            db_client=db_repo_container.db_client,
            cache_manager=db_repo_container.cache_manager,
            response_formatter=common_container.response_formatter,
        )

        plugins_container = PluginsContainer(
            db_client=db_repo_container.db_client,
            cloud_storage_manager=common_container.cloud_storage_manager,
            dynamic_query_repository=db_repo_container.dynamic_query_repository,
            cache_manager=db_repo_container.cache_manager,
        )

        bucket_name = AGENT_YAML_BUCKET

        tools_container = ToolsContainer(
            datasource_repository=db_repo_container.datasource_repository,
            knowledge_base_repository=db_repo_container.knowledge_base_repository,
            knowledge_base_inference_repository=db_repo_container.knowledge_base_inference_repository,
            message_processor_repository=plugins_container.message_processor_repository,
            api_services_manager=api_services_container.api_service_manager,
            cloud_storage_manager=common_container.cloud_storage_manager,
            message_processor_bucket_name=bucket_name,
        )

        llm_inference_config_container = LlmInferenceConfigContainer(
            db_client=db_repo_container.db_client,
            cache_manager=db_repo_container.cache_manager,
        )

        agents_container = AgentsContainer(
            db_client=db_repo_container.db_client,
            cloud_storage_manager=common_container.cloud_storage_manager,
            cache_manager=db_repo_container.cache_manager,
            tool_loader=tools_container.tool_loader,
            workflow_pipeline_repository=db_repo_container.workflow_pipeline_repository,
            workflow_runs_repository=db_repo_container.workflow_runs_repository,
            namespace_repository=db_repo_container.namespace_repository,
            agent_repository=db_repo_container.agent_repository,
            agent_version_repository=db_repo_container.agent_version_repository,
            workflow_repository=db_repo_container.workflow_repository,
            workflow_version_repository=db_repo_container.workflow_version_repository,
            message_processor_repository=plugins_container.message_processor_repository,
            message_processor_bucket_name=bucket_name,
            api_services_manager=api_services_container.api_service_manager,
            async_agentic_execution_repository=db_repo_container.async_agentic_execution_repository,
            executions_bucket=AGENTIC_EXECUTIONS_BUCKET,
            llm_inference_config_service=llm_inference_config_container.llm_inference_config_service,
        )

        # Inject config values from env vars so services like AgentCrudService
        # get the correct bucket_name via config.agents.agent_yaml_bucket
        agents_container.config.from_dict(
            {
                'agents': {'agent_yaml_bucket': bucket_name},
                'cloud_config': {'cloud_provider': CLOUD_PROVIDER},
                'workflow': {'worker_topic': WORKFLOW_WORKER_TOPIC},
            }
        )

        # Must use the same namespace as the floware app so stream keys match
        # floware's CacheManager uses config.env_config.app_name as its namespace
        cache = CacheManager(namespace=APP_NAME)

        triggers_container = TriggersContainer(
            trigger_repository=db_repo_container.agentic_trigger_repository,
            credential_repository=db_repo_container.agentic_trigger_credential_repository,
            event_repository=db_repo_container.agentic_trigger_event_repository,
            agent_repository=db_repo_container.agent_repository,
            workflow_repository=db_repo_container.workflow_repository,
            async_agentic_execution_service=agents_container.async_agentic_execution_service,
            cache_manager=db_repo_container.cache_manager,
        )
        triggers_container.config.from_dict(
            {
                'cloud_config': {'cloud_provider': CLOUD_PROVIDER},
                'triggers_gmail': {
                    'client_id': GOOGLE_OAUTH_CLIENT_ID,
                    'client_secret': GOOGLE_OAUTH_CLIENT_SECRET,
                    'redirect_uri': GOOGLE_OAUTH_REDIRECT_URI,
                    'pubsub_project_id': GCP_PROJECT_ID,
                    'pubsub_topic_prefix': GMAIL_PUBSUB_TOPIC_PREFIX,
                    'push_endpoint_template': GMAIL_PUSH_ENDPOINT_TEMPLATE,
                    'oidc_service_account_email': GMAIL_PUBSUB_OIDC_SA_EMAIL or None,
                },
            }
        )

        _services = WorkerServices(
            agent_inference=agents_container.agent_inference_service(),
            workflow_inference=agents_container.workflow_inference_service(),
            cloud_storage=common_container.cloud_storage_manager(),
            cache=cache,
            execution_bucket=AGENTIC_EXECUTIONS_BUCKET,
            trigger_event_processor=triggers_container.trigger_event_processor(),
        )

    return _services
