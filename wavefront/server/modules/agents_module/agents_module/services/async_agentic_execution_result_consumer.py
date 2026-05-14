import asyncio
import json
import os
import socket
from datetime import datetime
from typing import Optional
from uuid import UUID

from common_module.log.logger import logger
from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from db_repo_module.models.async_agentic_execution import AsyncAgenticExecution

_STREAM = os.getenv('ASYNC_AGENTIC_EXEC_RESULTS_STREAM', 'async_agentic_exec:results')
_GROUP = os.getenv('ASYNC_AGENTIC_EXEC_CONSUMER_GROUP', 'floware-agentic-consumers')
_CONSUMER = f'floware-{socket.gethostname()}'
_POLL_COUNT = 10
_BLOCK_MS = 1000

_STATUS_CACHE_TTL_TERMINAL = 3600
_STATUS_CACHE_KEY_PREFIX = 'async_agentic_exec:status'


class AsyncAgenticExecutionResultConsumer:
    """
    Background async task that runs inside the floware FastAPI app.
    Reads execution result events from a Redis Stream and writes them to DB.
    This is the only component that updates async_agentic_executions after the
    initial 'pending' record is created by AsyncAgenticExecutionService.

    Lifecycle:
        consumer = AsyncAgenticExecutionResultConsumer(exec_repo, cache_manager)
        task = asyncio.create_task(consumer.start())   # in app lifespan
        # on shutdown:
        consumer.stop()
        await task
    """

    def __init__(
        self,
        exec_repo: SQLAlchemyRepository[AsyncAgenticExecution],
        cache_manager: CacheManager,
    ):
        self._repo = exec_repo
        self._cache = cache_manager
        self._running = False

    async def start(self) -> None:
        """Entry point — call as asyncio.create_task(consumer.start())."""
        self._running = True

        # Create consumer group — idempotent, id='0' re-reads pending msgs on restart
        self._cache.xgroup_create(_STREAM, _GROUP, id='0', mkstream=True)
        logger.info(
            f'AsyncAgenticExecutionResultConsumer started — stream={_STREAM}, '
            f'group={_GROUP}, consumer={_CONSUMER}'
        )

        while self._running:
            try:
                messages = await asyncio.to_thread(
                    self._cache.xread_group,
                    _GROUP,
                    _CONSUMER,
                    {_STREAM: '>'},
                    _POLL_COUNT,
                    _BLOCK_MS,
                )

                for _stream_name, entries in messages:
                    for msg_id, fields in entries:
                        try:
                            await self._process(fields)
                            await asyncio.to_thread(
                                self._cache.xack, _STREAM, _GROUP, msg_id
                            )
                        except Exception as e:
                            logger.error(
                                f'Failed to process stream message {msg_id}: {e}. '
                                'Message will be redelivered on next consumer restart.'
                            )

            except Exception as e:
                logger.error(f'AsyncAgenticExecutionResultConsumer poll error: {e}')
                await asyncio.sleep(2)  # brief back-off before retrying

    def stop(self) -> None:
        self._running = False
        logger.info('AsyncAgenticExecutionResultConsumer stopping')

    async def _process(self, fields: dict) -> None:
        execution_id_str = fields.get('execution_id')
        status = fields.get('status')

        if not execution_id_str or not status:
            logger.warning(f'Stream message missing execution_id or status: {fields}')
            return

        execution_id = UUID(execution_id_str)

        # Build update kwargs — only include non-empty fields
        update_kwargs = {'status': status}

        if fields.get('started_at'):
            update_kwargs['started_at'] = _parse_dt(fields['started_at'])

        if fields.get('completed_at'):
            update_kwargs['completed_at'] = _parse_dt(fields['completed_at'])

        error = fields.get('error', '')
        if error:
            update_kwargs['error'] = error
        elif status in ('in_progress',):
            # Clear any previous error on retry
            update_kwargs['error'] = None

        if fields.get('output_file'):
            update_kwargs['output_file'] = fields['output_file']

        if fields.get('history_file'):
            update_kwargs['history_file'] = fields['history_file']

        if fields.get('input_bucket'):
            update_kwargs['input_bucket'] = fields['input_bucket']

        await self._repo.find_one_and_update({'id': execution_id}, **update_kwargs)

        logger.info(
            f'Updated async_agentic_executions: execution_id={execution_id}, status={status}'
        )

        # Update Redis status cache so the next poll is served from cache
        cache_key = f'{_STATUS_CACHE_KEY_PREFIX}:{execution_id}'
        if status in ('completed', 'failed'):
            # Fetch the full record and cache it for 1 hour
            record = await self._repo.find_one(id=execution_id)
            if record:
                await asyncio.to_thread(
                    self._cache.add,
                    cache_key,
                    json.dumps(record.to_dict()),
                    _STATUS_CACHE_TTL_TERMINAL,
                )
        else:
            # Invalidate stale cache so next GET hits DB
            await asyncio.to_thread(self._cache.remove, cache_key)


def _parse_dt(value: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
