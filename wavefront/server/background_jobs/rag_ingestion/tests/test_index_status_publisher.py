"""Tests for IndexStatusPublisher. The Redis CacheManager is a mock."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from db_repo_module.models.knowledge_base_documents import (
    KB_INDEX_STATUS_STREAM,
    IndexStatus,
)
from rag_ingestion.service.index_status_publisher import IndexStatusPublisher


def make_publisher():
    cache = MagicMock()
    cache.namespace = 'floware'
    cache.xadd.return_value = '1-0'
    return IndexStatusPublisher(cache), cache


def test_publishes_status_event_to_the_stream():
    publisher, cache = make_publisher()

    assert publisher.publish('doc-1', 'kb-1', IndexStatus.FAILED, error='boom') is True

    stream, fields = cache.xadd.call_args.args
    assert stream == KB_INDEX_STATUS_STREAM
    assert fields['doc_id'] == 'doc-1'
    assert fields['kb_id'] == 'kb-1'
    assert fields['status'] == 'FAILED'
    assert fields['error'] == 'boom'
    at = datetime.fromisoformat(fields['at'])
    assert at.tzinfo is not None
    assert abs((datetime.now(timezone.utc) - at).total_seconds()) < 5


def test_all_field_values_are_strings_for_redis():
    publisher, cache = make_publisher()

    publisher.publish('doc-1', None, IndexStatus.COMPLETE)

    _, fields = cache.xadd.call_args.args
    assert all(isinstance(v, str) for v in fields.values())
    assert fields['kb_id'] == '' and fields['error'] == ''


def test_long_errors_are_truncated():
    publisher, cache = make_publisher()

    publisher.publish('doc-1', 'kb-1', IndexStatus.FAILED, error='x' * 5000)

    _, fields = cache.xadd.call_args.args
    assert len(fields['error']) == 2000


def test_returns_false_when_redis_fails():
    publisher, cache = make_publisher()
    cache.xadd.side_effect = ConnectionError('redis down')

    assert publisher.publish('doc-1', 'kb-1', IndexStatus.COMPLETE) is False
