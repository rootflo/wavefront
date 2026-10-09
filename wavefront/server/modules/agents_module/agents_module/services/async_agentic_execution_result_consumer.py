import asyncio
import json
import socket
import time
from datetime import datetime
from typing import Optional
from uuid import UUID

from common_module.log.logger import logger
from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from db_repo_module.models.async_agentic_execution import AsyncAgenticExecution

_CONSUMER = f'floware-{socket.gethostname()}'
_POLL_COUNT = 10

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
        *,
        stream: str = 'async_agentic_exec:results',
        group: str = 'floware-agentic-consumers',
        poll_interval_s: float = 5.0,
        heartbeat_interval_s: int = 60,
    ):
        self._repo = exec_repo
        self._cache = cache_manager
        self._stream = stream
        self._group = group
        self._poll_interval_s = poll_interval_s
        self._heartbeat_interval_s = heartbeat_interval_s
        self._running = False
        self._stop_requested = asyncio.Event()

    async def start(self) -> None:
        """Entry point — call as asyncio.create_task(consumer.start())."""
        try:
            await self._run_forever()
        except asyncio.CancelledError:
            logger.warning('AsyncAgenticExecutionResultConsumer cancelled')
            raise
        except BaseException:
            # Nothing awaits this task while the app runs, so without this the
            # loop can die and stay dead with no trace until interpreter exit.
            logger.exception(
                'AsyncAgenticExecutionResultConsumer died — status updates '
                'will stop until floware is restarted'
            )
            raise

    async def _run_forever(self) -> None:
        self._running = True

        # Create consumer group — idempotent. id='0' only sets the initial cursor
        # when the group is first created; subsequent calls are no-ops (BUSYGROUP
        # silently ignored). PEL entries from a previous run are NOT auto-redelivered
        # by this call — a separate XAUTOCLAIM/XCLAIM pass would be needed for that.
        self._cache.xgroup_create(self._stream, self._group, id='0', mkstream=True)

        # Log the RESOLVED key, not self._stream. CacheManager prepends its namespace
        # inside xadd/xreadgroup, so a publisher and consumer configured with
        # different APP_NAMEs use different Redis keys while logging the same
        # stream name — a mismatch that is otherwise invisible in the logs.
        resolved_key = f'{self._cache.namespace}/{self._stream}'
        logger.info(
            f'AsyncAgenticExecutionResultConsumer started — key={resolved_key}, '
            f'group={self._group}, consumer={_CONSUMER}'
        )

        polls = 0
        received = 0
        last_heartbeat = time.monotonic()

        while self._running:
            try:
                messages = await asyncio.to_thread(
                    self._cache.xread_group,
                    self._group,
                    _CONSUMER,
                    {self._stream: '>'},
                    _POLL_COUNT,
                    None,  # don't block: hold the pooled connection for one round trip
                )
                polls += 1
                batch_size = sum(len(entries) for _stream, entries in messages)
                received += batch_size

                # Heartbeat distinguishes "loop is dead" from "loop is alive but
                # this key never yields anything".
                now = time.monotonic()
                if now - last_heartbeat >= self._heartbeat_interval_s:
                    last_heartbeat = now
                    logger.info(
                        f'Consumer alive — consumer={_CONSUMER}, '
                        f'key={resolved_key}, polls={polls}, '
                        f'messages_received={received}'
                    )

                for _stream_name, entries in messages:
                    for msg_id, fields in entries:
                        # Receipt log, paired with the publisher's 'Published
                        # result event ... message_id=' line. Without both ends
                        # a missing status update cannot be attributed to the
                        # publisher or to this consumer.
                        logger.info(
                            f'Received stream message {msg_id}: '
                            f'execution_id={fields.get("execution_id")}, '
                            f'status={fields.get("status")}'
                        )
                        try:
                            await self._process(fields)
                            await asyncio.to_thread(
                                self._cache.xack, self._stream, self._group, msg_id
                            )
                        except Exception as e:
                            logger.error(
                                f'Failed to process stream message {msg_id}: {e}. '
                                'Message remains in PEL until a claim/drain runs.'
                            )

                # A full batch means more may be waiting: read again straight
                # away. Otherwise the stream is drained, so wait.
                if batch_size < _POLL_COUNT and self._running:
                    await self._sleep(self._poll_interval_s)

            except Exception as e:
                logger.error(f'AsyncAgenticExecutionResultConsumer poll error: {e}')
                await self._sleep(
                    max(self._poll_interval_s, 2)
                )  # back off before retrying

    async def _sleep(self, seconds: float) -> None:
        """Sleep, returning early if stop() is called."""
        try:
            await asyncio.wait_for(self._stop_requested.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    def stop(self) -> None:
        self._running = False
        self._stop_requested.set()  # wake the loop if it is sleeping between polls
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
