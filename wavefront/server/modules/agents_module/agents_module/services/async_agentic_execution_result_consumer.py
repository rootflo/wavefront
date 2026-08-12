import asyncio
import json
import os
import socket
import time
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

# Reclaim entries left unacked in the PEL. min-idle is well above the time a
# healthy _process takes, so we never steal a message another consumer is
# actively working on.
_CLAIM_MIN_IDLE_MS = int(os.getenv('ASYNC_AGENTIC_EXEC_CLAIM_MIN_IDLE_MS', '60000'))
_CLAIM_INTERVAL_S = int(os.getenv('ASYNC_AGENTIC_EXEC_CLAIM_INTERVAL_S', '30'))

# A message that can never be processed would otherwise be reclaimed forever.
# After this many delivery attempts it is logged in full and acked, so the
# stream keeps moving; the affected row then needs manual reconciliation.
_MAX_DELIVERIES = int(os.getenv('ASYNC_AGENTIC_EXEC_MAX_DELIVERIES', '5'))

_STATUS_CACHE_TTL_TERMINAL = 3600
_STATUS_CACHE_KEY_PREFIX = 'async_agentic_exec:status'

_TERMINAL_STATUSES = ('completed', 'failed')


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
        self._last_claim = 0.0

    async def start(self) -> None:
        """Entry point — call as asyncio.create_task(consumer.start())."""
        self._running = True

        # Create consumer group — idempotent. id='0' only sets the initial cursor
        # when the group is first created; subsequent calls are no-ops (BUSYGROUP
        # silently ignored). Entries already sitting in the PEL are recovered by
        # the _reclaim_stale() pass below, not by this call.
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
                    await self._handle_entries(entries)

                await self._maybe_reclaim()

            except asyncio.CancelledError:
                # Never swallow cancellation — anything unacked is left in the
                # PEL on purpose and picked up by the next reclaim pass.
                logger.warning(
                    'AsyncAgenticExecutionResultConsumer cancelled; '
                    'unacked messages left in PEL for reclaim'
                )
                raise
            except Exception as e:
                logger.error(f'AsyncAgenticExecutionResultConsumer poll error: {e}')
                await asyncio.sleep(2)  # brief back-off before retrying

    def stop(self) -> None:
        self._running = False
        logger.info('AsyncAgenticExecutionResultConsumer stopping')

    async def _handle_entries(self, entries) -> None:
        """Process then ack each entry. Anything not acked stays in the PEL."""
        for msg_id, fields in entries:
            if not fields:
                # Payload was trimmed out of the stream (xadd maxlen). Nothing
                # to apply, but ack so it stops being reclaimed forever.
                logger.warning(f'Stream message {msg_id} has no payload; acking')
                await self._ack(msg_id)
                continue

            try:
                await self._process(fields)
            except asyncio.CancelledError:
                logger.warning(
                    f'Cancelled while processing stream message {msg_id}; '
                    'left unacked for reclaim'
                )
                raise
            except Exception as e:
                logger.error(
                    f'Failed to process stream message {msg_id}: {e}. '
                    'Left in PEL for reclaim.'
                )
                await self._drop_if_exhausted(msg_id, fields)
                continue

            await self._ack(msg_id)

    async def _drop_if_exhausted(self, msg_id, fields) -> bool:
        """Ack a message that has failed too many times, so it stops recycling.

        Only consulted on the failure path, so the extra round-trip is rare.
        Dropping loses the update — the payload is logged in full so the row can
        be reconciled by hand.
        """
        try:
            pending = await asyncio.to_thread(
                self._cache.xpending_range, _STREAM, _GROUP, msg_id, msg_id, 1
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f'Could not read delivery count for {msg_id}: {e}')
            return False

        if not pending:
            return False

        delivered = pending[0].get('times_delivered', 0)
        if delivered < _MAX_DELIVERIES:
            return False

        logger.error(
            f'Dropping stream message {msg_id} after {delivered} failed '
            f'deliveries — execution row needs manual reconciliation. '
            f'Payload: {fields}'
        )
        await self._ack(msg_id)
        return True

    async def _ack(self, msg_id) -> None:
        try:
            await asyncio.to_thread(self._cache.xack, _STREAM, _GROUP, msg_id)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            # Already applied to the DB — reclaim will re-run it, which is safe
            # because _process is idempotent.
            logger.error(f'Processed but failed to ack stream message {msg_id}: {e}')

    async def _maybe_reclaim(self) -> None:
        now = time.monotonic()
        if now - self._last_claim < _CLAIM_INTERVAL_S:
            return
        self._last_claim = now
        await self._reclaim_stale()

    async def _reclaim_stale(self) -> None:
        """Take over PEL entries idle past the threshold and re-run them.

        Covers messages stranded by a crashed/cancelled consumer, including ones
        owned by consumer names that no longer exist (every pod roll creates one,
        since _CONSUMER is hostname-derived).
        """
        start_id = '0-0'
        reclaimed = 0

        while self._running:
            next_id, entries = await asyncio.to_thread(
                self._cache.xautoclaim,
                _STREAM,
                _GROUP,
                _CONSUMER,
                _CLAIM_MIN_IDLE_MS,
                start_id,
                _POLL_COUNT,
            )

            if entries:
                reclaimed += len(entries)
                await self._handle_entries(entries)

            next_id = next_id.decode() if isinstance(next_id, bytes) else str(next_id)
            if next_id == '0-0':
                break
            start_id = next_id

        if reclaimed:
            logger.info(f'Reclaimed {reclaimed} stale stream message(s) from PEL')

    async def _process(self, fields: dict) -> None:
        execution_id_str = fields.get('execution_id')
        status = fields.get('status')

        if not execution_id_str or not status:
            logger.warning(f'Stream message missing execution_id or status: {fields}')
            return

        execution_id = UUID(execution_id_str)

        # Reclaim can deliver out of order — a stale 'in_progress' must never
        # overwrite a row that already reached a terminal state.
        if status not in _TERMINAL_STATUSES:
            current = await self._repo.find_one(id=execution_id)
            if current and current.status in _TERMINAL_STATUSES:
                logger.info(
                    f'Ignoring {status} update for execution_id={execution_id}: '
                    f'already {current.status}'
                )
                return

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
        if status in _TERMINAL_STATUSES:
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
