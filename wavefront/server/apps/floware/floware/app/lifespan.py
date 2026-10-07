"""FastAPI lifespan: DB connect, background consumers, graceful shutdown."""

from contextlib import asynccontextmanager
import asyncio

from agents_module.services.async_agentic_execution_result_consumer import (
    AsyncAgenticExecutionResultConsumer,
)
from common_module.log.logger import logger
from common_module.telemetry import instrument_sqlalchemy, shutdown_telemetry
from db_repo_module.database.connection import DatabaseClient
from fastapi import FastAPI
from floware.app.channels import start_redis_listener
from floware.di.containers import (
    api_services_container,
    application_container,
    config,
    db_repo_container,
    guardrails_container,
    knowledge_base_container,
    scheduler_manager,
)
from knowledge_base_module.services.kb_index_status_consumer import (
    KbIndexStatusConsumer,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup code (runs before the application starts)
    logger.info('Starting application...')

    try:
        db_client: DatabaseClient = db_repo_container.db_client()

        if isinstance(db_client, DatabaseClient):
            logger.info('========== Establishing db connection ...')
            await db_client.connect()
            logger.info('========== DB connection established.')
            # Emits db.* spans for every query; needs the engine, so it can
            # only happen once the DI container has built the client.
            instrument_sqlalchemy(db_client.engine)
        else:
            raise TypeError('db_client is not an instance of DatabaseClient')

        db_client.run_migration()

        # Load the safety providers' models before the first request needs
        # them. Presidio builds a spaCy model on first use, which takes longer
        # than the per-check timeout the policy sets — so without this the
        # first checked request times out and, under a FAIL_CLOSED policy, is
        # rejected. Paid here, where nothing is waiting on it. No-op when the
        # container was not constructed ([guardrails] enabled=false).
        if guardrails_container is not None:
            await guardrails_container.guardrails_engine().warmup()

        scheduled_job_service = application_container.scheduled_job_service()

        # Run stale lock recovery once on startup before the scheduler ticks.
        await scheduled_job_service.recover_stale_locks()

        scheduler_manager.start()
        scheduler_manager.register_due_jobs_poller(
            callback=scheduled_job_service.process_due_jobs_sync
        )
        scheduler_manager.register_stale_lock_recovery(
            callback=scheduled_job_service.recover_stale_locks_sync
        )
        logger.info('Database connection established.')

        # Load API services from database into registry
        service_registry = api_services_container.initialized_service_registry()
        if getattr(service_registry, 'api_service_manager', None):
            try:
                await service_registry.load_from_db()
                logger.info('API services loaded from database')

                # Reload routes to include newly loaded services
                proxy_router = api_services_container.proxy_router()
                proxy_router.reload_routes()
                logger.info('API service routes reloaded')
            except Exception as e:
                logger.warning(f'Failed to load API services from database: {e}')

        api_services_container.initialized_proxy()

        # Include API services router AFTER services are loaded so routes are registered
        # This ensures FastAPI's route table includes the dynamic routes
        app.include_router(
            api_services_container.router(), tags=['API Services'], prefix='/floware'
        )
        logger.info('API services router included in app')

        # Start background Redis listener for updates
        asyncio.create_task(
            start_redis_listener(
                cache_manager=db_repo_container.cache_manager(),
                api_change_processor=api_services_container.api_change_processor(),
            )
        )

        # Start Redis Stream consumer for async execution status updates
        streams = config['streams']
        consumer_shutdown_timeout_s = float(streams['consumer_shutdown_timeout_s'])
        async_agentic_exec_consumer = AsyncAgenticExecutionResultConsumer(
            exec_repo=db_repo_container.async_agentic_execution_repository(),
            cache_manager=db_repo_container.cache_manager(),
            stream=streams['async_agentic_exec_results'],
            group=streams['async_agentic_exec_consumer_group'],
            poll_interval_s=float(streams['async_agentic_exec_poll_interval_s']),
            heartbeat_interval_s=int(streams['async_agentic_exec_heartbeat_s']),
        )
        async_agentic_exec_consumer_task = asyncio.create_task(
            async_agentic_exec_consumer.start()
        )

        # Start Redis Stream consumer for knowledge base document index statuses
        kb_index_status_consumer = KbIndexStatusConsumer(
            documents_repo=knowledge_base_container.knowledge_base_documents_repository(),
            cache_manager=db_repo_container.cache_manager(),
            group=streams['kb_index_status_consumer_group'],
            poll_interval_s=float(streams['kb_index_status_poll_interval_s']),
            heartbeat_interval_s=int(streams['kb_index_status_heartbeat_s']),
            reclaim_interval_s=float(streams['kb_index_status_reclaim_interval_s']),
            reclaim_min_idle_ms=int(streams['kb_index_status_reclaim_min_idle_ms']),
            max_deliveries=int(streams['kb_index_status_max_deliveries']),
        )
        kb_index_status_consumer_task = asyncio.create_task(
            kb_index_status_consumer.start()
        )

        # Set app reference in proxy router so new routes can be added dynamically
        proxy_router = api_services_container.proxy_router()
        proxy_router.set_app(app, prefix='/floware')
        logger.info('App reference set in proxy router for dynamic route registration')

        yield  # This is where the application runs

        # Shutdown code
        scheduler_manager.shutdown()
        async_agentic_exec_consumer.stop()
        try:
            await asyncio.wait_for(
                async_agentic_exec_consumer_task, timeout=consumer_shutdown_timeout_s
            )
        except asyncio.TimeoutError:
            async_agentic_exec_consumer_task.cancel()
            logger.warning(
                'AsyncAgenticExecutionResultConsumer did not stop within '
                f'{consumer_shutdown_timeout_s}s; cancelled'
            )
        kb_index_status_consumer.stop()
        try:
            await asyncio.wait_for(
                kb_index_status_consumer_task, timeout=consumer_shutdown_timeout_s
            )
        except asyncio.TimeoutError:
            kb_index_status_consumer_task.cancel()
            logger.warning(
                'KbIndexStatusConsumer did not stop within '
                f'{consumer_shutdown_timeout_s}s; cancelled'
            )
        logger.info('Shutting down application...')

    except Exception as e:
        logger.error(f'Error during application lifecycle: {str(e)}')
        raise
    finally:
        # In a `finally` so buffered spans and metrics are still flushed when
        # shutdown takes an error path or startup fails before `yield`.
        shutdown_telemetry()
