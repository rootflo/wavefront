import asyncio
import os
import socket
import time
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from common_module.log.logger import logger
from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.models.knowledge_base_documents import (
    KB_INDEX_STATUS_STREAM,
    IndexStatus,
    KnowledgeBaseDocuments,
)
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from sqlalchemy import or_, update

_GROUP = os.getenv('KB_INDEX_STATUS_CONSUMER_GROUP', 'floware-kb-index-status')
_CONSUMER = f'floware-{socket.gethostname()}'
_POLL_COUNT = 50
# Seconds to wait after a poll that did not fill a batch. Each poll is a
# non-blocking read, so the shared Redis pool connection is only borrowed for
# one round trip; status updates can lag by up to this much.
_POLL_INTERVAL_S = float(os.getenv('KB_INDEX_STATUS_POLL_INTERVAL_S', '5'))
_HEARTBEAT_INTERVAL_S = int(os.getenv('KB_INDEX_STATUS_HEARTBEAT_S', '60'))

# Recovery of events that were delivered but never acknowledged (processing
# failed, or the replica holding them died): every _RECLAIM_INTERVAL_S, entries
# idle for _RECLAIM_MIN_IDLE_MS are claimed from any consumer and applied
# again. An entry delivered _MAX_DELIVERIES times is acknowledged and dropped,
# so one that can never be applied doesn't stay pending forever.
_RECLAIM_INTERVAL_S = float(os.getenv('KB_INDEX_STATUS_RECLAIM_INTERVAL_S', '60'))
_RECLAIM_MIN_IDLE_MS = int(os.getenv('KB_INDEX_STATUS_RECLAIM_MIN_IDLE_MS', '60000'))
_MAX_DELIVERIES = int(os.getenv('KB_INDEX_STATUS_MAX_DELIVERIES', '5'))

_VALID_STATUSES = {status.value for status in IndexStatus}


class KbIndexStatusConsumer:
    """
    Background task in floware that applies document index status events from
    the rag_ingestion worker to knowledge_base_documents.

    The worker appends {doc_id, status, at, error} to KB_INDEX_STATUS_STREAM.
    A consumer group delivers each event to one floware replica, and an event
    is acknowledged only after it is applied, so none are lost while floware
    restarts (unlike Redis pub/sub). Events left unacknowledged -- processing
    failed, or the replica holding them died -- are replayed on startup and
    reclaimed when idle, up to _MAX_DELIVERIES attempts.

    Events from different replicas or retries can be applied out of order, so
    each update only lands if its `at` is newer than the stored
    index_status_updated_at: a late IN_PROGRESS never overwrites COMPLETE.

    Lifecycle:
        consumer = KbIndexStatusConsumer(documents_repo, cache_manager)
        task = asyncio.create_task(consumer.start())   # in app lifespan
        # on shutdown:
        consumer.stop()
        await task
    """

    def __init__(
        self,
        documents_repo: SQLAlchemyRepository[KnowledgeBaseDocuments],
        cache_manager: CacheManager,
    ):
        self._repo = documents_repo
        self._cache = cache_manager
        self._running = False
        self._stop_requested = asyncio.Event()

    async def start(self) -> None:
        """Entry point — call as asyncio.create_task(consumer.start())."""
        try:
            await self._run_forever()
        except asyncio.CancelledError:
            logger.warning('KbIndexStatusConsumer cancelled')
            raise
        except BaseException:
            # Nothing awaits this task while the app runs, so without this the
            # loop could die silently.
            logger.exception(
                'KbIndexStatusConsumer died — document index statuses will stop '
                'updating until floware is restarted'
            )
            raise

    def stop(self) -> None:
        self._running = False
        self._stop_requested.set()  # wake the loop if it is sleeping between polls
        logger.info('KbIndexStatusConsumer stopping')

    async def _run_forever(self) -> None:
        self._running = True
        self._cache.xgroup_create(KB_INDEX_STATUS_STREAM, _GROUP, id='0', mkstream=True)

        # Log the resolved key: CacheManager prepends its namespace, and the
        # worker must publish under the same one (its FLOWARE_APP_NAME).
        resolved_key = f'{self._cache.namespace}/{KB_INDEX_STATUS_STREAM}'
        logger.info(
            f'KbIndexStatusConsumer started — key={resolved_key}, '
            f'group={_GROUP}, consumer={_CONSUMER}'
        )

        # Events this consumer received before a restart but never acknowledged
        await self._drain_own_pending()

        polls = 0
        received = 0
        last_heartbeat = time.monotonic()
        last_reclaim = time.monotonic()

        while self._running:
            try:
                now = time.monotonic()
                if now - last_reclaim >= _RECLAIM_INTERVAL_S:
                    last_reclaim = now
                    await self._reclaim_idle()

                messages = await asyncio.to_thread(
                    self._cache.xread_group,
                    _GROUP,
                    _CONSUMER,
                    {KB_INDEX_STATUS_STREAM: '>'},
                    _POLL_COUNT,
                    None,  # don't block: hold the pooled connection for one round trip
                )
                polls += 1
                batch_size = sum(len(entries) for _stream, entries in messages)
                received += batch_size

                if now - last_heartbeat >= _HEARTBEAT_INTERVAL_S:
                    last_heartbeat = now
                    logger.info(
                        f'KbIndexStatusConsumer alive — key={resolved_key}, '
                        f'polls={polls}, messages_received={received}'
                    )

                for _stream_name, entries in messages:
                    for msg_id, fields in entries:
                        await self._apply_and_ack(msg_id, fields)

                # A full batch means more may be waiting: read again straight
                # away. Otherwise the stream is drained, so wait.
                if batch_size < _POLL_COUNT and self._running:
                    await self._sleep(_POLL_INTERVAL_S)
            except Exception as e:
                logger.error(f'KbIndexStatusConsumer poll error: {e}')
                await self._sleep(max(_POLL_INTERVAL_S, 2))

    async def _apply_and_ack(self, msg_id: str, fields: Optional[dict]) -> None:
        """Apply one event and acknowledge it. On failure it stays pending and
        is retried by _reclaim_idle once idle."""
        if not fields:
            # Trimmed from the stream while pending: nothing left to apply
            await self._ack(msg_id)
            return
        try:
            await self.process(fields)
            await self._ack(msg_id)
        except Exception as e:
            logger.error(
                f'Failed to apply index status message {msg_id} ({fields}): {e}. '
                'It stays pending and will be retried.'
            )

    async def _ack(self, *msg_ids: str) -> None:
        await asyncio.to_thread(
            self._cache.xack, KB_INDEX_STATUS_STREAM, _GROUP, *msg_ids
        )

    async def _pending(self, **filters) -> list:
        return await asyncio.to_thread(
            self._cache.xpending_range,
            KB_INDEX_STATUS_STREAM,
            _GROUP,
            _POLL_COUNT,
            **filters,
        )

    async def _drop_exhausted(self, pending: list) -> set:
        """Acknowledge (drop) pending entries already delivered _MAX_DELIVERIES
        times. Returns their ids."""
        exhausted = {
            str(entry['message_id'])
            for entry in pending
            if entry.get('times_delivered', 0) >= _MAX_DELIVERIES
        }
        if exhausted:
            logger.error(
                f'Dropping {len(exhausted)} index status event(s) after '
                f'{_MAX_DELIVERIES} failed deliveries: {sorted(exhausted)}'
            )
            await self._ack(*exhausted)
        return exhausted

    async def _drain_own_pending(self) -> None:
        """Replay this consumer's own pending entries (read from ID 0) once,
        e.g. after a restart. The cursor moves past each entry, so one that
        fails again is left for _reclaim_idle rather than retried in a loop."""
        cursor = '0'
        while self._running:
            try:
                exhausted = await self._drop_exhausted(
                    await self._pending(consumer=_CONSUMER, start=cursor)
                )
                messages = await asyncio.to_thread(
                    self._cache.xread_group,
                    _GROUP,
                    _CONSUMER,
                    {KB_INDEX_STATUS_STREAM: cursor},
                    _POLL_COUNT,
                    None,
                )
            except Exception as e:
                logger.error(
                    f'KbIndexStatusConsumer could not read pending entries: {e}'
                )
                return
            entries = [entry for _stream, batch in messages for entry in batch]
            if not entries:
                return
            for msg_id, fields in entries:
                if str(msg_id) not in exhausted:
                    await self._apply_and_ack(msg_id, fields)
            cursor = str(entries[-1][0])
            if len(entries) < _POLL_COUNT:
                return

    async def _reclaim_idle(self) -> None:
        """Retry entries left pending by failed processing or by a replica
        that died: drop those out of deliveries, claim the rest, apply them."""
        try:
            await self._drop_exhausted(
                await self._pending(min_idle_ms=_RECLAIM_MIN_IDLE_MS)
            )
            claimed = await asyncio.to_thread(
                self._cache.xautoclaim,
                KB_INDEX_STATUS_STREAM,
                _GROUP,
                _CONSUMER,
                _RECLAIM_MIN_IDLE_MS,
                '0-0',
                _POLL_COUNT,
            )
        except Exception as e:
            logger.error(f'KbIndexStatusConsumer could not reclaim idle entries: {e}')
            return
        if claimed:
            logger.info(f'Reclaimed {len(claimed)} idle index status event(s)')
        for msg_id, fields in claimed:
            await self._apply_and_ack(msg_id, fields)

    async def _sleep(self, seconds: float) -> None:
        """Sleep, returning early if stop() is called."""
        try:
            await asyncio.wait_for(self._stop_requested.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    async def process(self, fields: dict) -> bool:
        """Apply one status event. Returns True if it changed the document.

        Malformed events are logged and dropped (returning False) rather than
        raised, so they are acknowledged instead of retried forever.
        """
        doc_id_str = fields.get('doc_id')
        status = fields.get('status')
        at = _parse_utc(fields.get('at'))
        if not doc_id_str or status not in _VALID_STATUSES or at is None:
            logger.warning(f'Dropping malformed index status event: {fields}')
            return False
        try:
            doc_id = UUID(doc_id_str)
        except ValueError:
            logger.warning(f'Dropping index status event with bad doc_id: {fields}')
            return False

        error = fields.get('error') or None
        model = KnowledgeBaseDocuments
        statement = (
            update(model)
            .where(model.id == doc_id)
            .where(
                or_(
                    model.index_status_updated_at.is_(None),
                    model.index_status_updated_at < at,
                )
            )
            .values(
                index_status=status,
                index_error=error if status == IndexStatus.FAILED.value else None,
                index_status_updated_at=at,
            )
        )
        async with self._repo.session() as session:
            result = await session.execute(statement)
            await session.commit()

        if result.rowcount:
            logger.info(f'Document {doc_id} index status -> {status}')
            return True
        logger.info(
            f'Ignored index status {status} for document {doc_id}: document '
            'missing or a newer status is already recorded'
        )
        return False


def _parse_utc(value: Optional[str]) -> Optional[datetime]:
    """ISO timestamp -> naive UTC datetime (the column has no time zone)."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed
