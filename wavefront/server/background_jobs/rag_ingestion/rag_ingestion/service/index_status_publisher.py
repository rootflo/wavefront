from datetime import datetime, timezone
from typing import Optional

from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.models.knowledge_base_documents import (
    KB_INDEX_STATUS_STREAM,
    IndexStatus,
)
from flo_utils.utils.log import logger


class IndexStatusPublisher:
    """Reports document index status to floware over a Redis Stream.

    floware's KbIndexStatusConsumer applies these events to
    knowledge_base_documents. The CacheManager must use floware's namespace
    (FLOWARE_APP_NAME), not the worker's own, or floware never sees them.
    """

    def __init__(self, cache_manager: CacheManager):
        self._cache = cache_manager
        logger.info(
            'Publishing document index status to '
            f'{cache_manager.namespace}/{KB_INDEX_STATUS_STREAM}'
        )

    def publish(
        self,
        doc_id: str,
        kb_id: Optional[str],
        status: IndexStatus,
        error: Optional[str] = None,
    ) -> bool:
        """Append one status event. Returns False (and logs) if it could not be
        sent; callers decide whether that matters."""
        fields = {
            'doc_id': str(doc_id),
            'kb_id': str(kb_id or ''),
            'status': status.value,
            # Worker-side time; floware applies an event only if it is newer
            # than the last one it applied for the document.
            'at': datetime.now(timezone.utc).isoformat(),
            'error': (error or '')[:2000],
        }
        try:
            message_id = self._cache.xadd(KB_INDEX_STATUS_STREAM, fields)
        except Exception as err:
            logger.error(
                f'Failed to publish index status {status.value} for doc {doc_id}: {err}'
            )
            return False
        logger.info(
            f'Published index status {status.value} for doc {doc_id} '
            f'(message_id={message_id})'
        )
        return True
