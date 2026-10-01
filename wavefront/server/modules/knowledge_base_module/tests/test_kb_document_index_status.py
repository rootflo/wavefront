"""
Tests for knowledge base document index status: floware marks documents
QUEUED (or FAILED) on upload, and KbIndexStatusConsumer applies the
rag_ingestion worker's status events. DB-backed; Redis and the message queue
are mocks.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from db_repo_module.models.knowledge_base_documents import (
    KB_INDEX_STATUS_STREAM,
    IndexStatus,
    KnowledgeBaseDocuments,
)
from db_repo_module.models.knowledge_bases import KnowledgeBase
from fastapi import status
from flo_testing import seed_user_session as create_session
from knowledge_base_module.services.kb_index_status_consumer import (
    KbIndexStatusConsumer,
)
from sqlalchemy import select

T0 = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
async def seeded(test_session, test_user_id, test_session_id):
    await create_session(test_session, test_user_id, test_session_id)


@pytest.fixture
def kb_container(setup_containers):
    return setup_containers[3]


@pytest.fixture
def consumer(kb_container):
    return KbIndexStatusConsumer(
        documents_repo=kb_container.knowledge_base_documents_repository(),
        cache_manager=MagicMock(namespace='floware'),
    )


async def create_kb(test_session) -> UUID:
    kb_id = uuid4()
    async with test_session() as session:
        session.add(
            KnowledgeBase(
                id=kb_id,
                name=f'KB {kb_id}',
                description='index status test',
                type='document',
                vector_size=3,
            )
        )
        await session.commit()
    return kb_id


async def create_doc(test_session, index_status=IndexStatus.QUEUED.value) -> UUID:
    kb_id = await create_kb(test_session)
    doc_id = uuid4()
    async with test_session() as session:
        session.add(
            KnowledgeBaseDocuments(
                id=doc_id,
                knowledge_base_id=kb_id,
                file_path=f'bucket/{doc_id}',
                file_name='doc.txt',
                file_type='plain',
                file_size=10,
                index_status=index_status,
            )
        )
        await session.commit()
    return doc_id


async def get_doc(test_session, doc_id) -> KnowledgeBaseDocuments:
    async with test_session() as session:
        return await session.scalar(
            select(KnowledgeBaseDocuments).where(KnowledgeBaseDocuments.id == doc_id)
        )


def event(doc_id, status_value: IndexStatus, at: datetime, error: str = ''):
    return {
        'doc_id': str(doc_id),
        'kb_id': '',
        'status': status_value.value,
        'at': at.isoformat(),
        'error': error,
    }


class TestConsumerProcess:
    async def test_applies_status_updates_in_order(
        self, seeded, consumer, test_session
    ):
        doc_id = await create_doc(test_session)

        assert await consumer.process(event(doc_id, IndexStatus.IN_PROGRESS, T0))
        assert (await get_doc(test_session, doc_id)).index_status == 'IN_PROGRESS'

        later = T0 + timedelta(seconds=5)
        assert await consumer.process(event(doc_id, IndexStatus.COMPLETE, later))

        doc = await get_doc(test_session, doc_id)
        assert doc.index_status == 'COMPLETE'
        assert doc.index_status_updated_at == later.replace(tzinfo=None)

    async def test_older_event_does_not_overwrite_newer_status(
        self, seeded, consumer, test_session
    ):
        doc_id = await create_doc(test_session)
        await consumer.process(event(doc_id, IndexStatus.COMPLETE, T0))

        # a delayed IN_PROGRESS from earlier arrives after COMPLETE
        applied = await consumer.process(
            event(doc_id, IndexStatus.IN_PROGRESS, T0 - timedelta(seconds=3))
        )

        assert applied is False
        assert (await get_doc(test_session, doc_id)).index_status == 'COMPLETE'

    async def test_failed_records_the_error_and_success_clears_it(
        self, seeded, consumer, test_session
    ):
        doc_id = await create_doc(test_session)

        await consumer.process(event(doc_id, IndexStatus.FAILED, T0, error='bad image'))
        doc = await get_doc(test_session, doc_id)
        assert (doc.index_status, doc.index_error) == ('FAILED', 'bad image')

        await consumer.process(
            event(doc_id, IndexStatus.COMPLETE, T0 + timedelta(seconds=1), error='x')
        )
        doc = await get_doc(test_session, doc_id)
        assert (doc.index_status, doc.index_error) == ('COMPLETE', None)

    async def test_naive_and_offset_timestamps_are_compared_in_utc(
        self, seeded, consumer, test_session
    ):
        doc_id = await create_doc(test_session)
        await consumer.process(event(doc_id, IndexStatus.IN_PROGRESS, T0))

        # 12:00:02 UTC expressed as 17:30:02+05:30
        ist = timezone(timedelta(hours=5, minutes=30))
        later_in_ist = (T0 + timedelta(seconds=2)).astimezone(ist)
        assert await consumer.process(event(doc_id, IndexStatus.COMPLETE, later_in_ist))

    async def test_unknown_document_is_ignored(self, seeded, consumer):
        assert await consumer.process(event(uuid4(), IndexStatus.COMPLETE, T0)) is False

    @pytest.mark.parametrize(
        'fields',
        [
            {},
            {'doc_id': 'not-a-uuid', 'status': 'COMPLETE', 'at': T0.isoformat()},
            {'doc_id': str(uuid4()), 'status': 'DONE', 'at': T0.isoformat()},
            {'doc_id': str(uuid4()), 'status': 'COMPLETE', 'at': 'yesterday'},
        ],
    )
    async def test_malformed_events_are_dropped(self, seeded, consumer, fields):
        assert await consumer.process(fields) is False


async def test_consumer_loop_acks_after_applying(seeded, kb_container, test_session):
    doc_id = await create_doc(test_session)
    cache = MagicMock(namespace='floware')
    consumer = KbIndexStatusConsumer(
        kb_container.knowledge_base_documents_repository(), cache
    )

    def read_once(*args):
        consumer.stop()
        return [
            (
                KB_INDEX_STATUS_STREAM,
                [('1-0', event(doc_id, IndexStatus.COMPLETE, T0))],
            )
        ]

    cache.xread_group.side_effect = read_once

    await asyncio.wait_for(consumer.start(), timeout=10)

    cache.xgroup_create.assert_called_once()
    cache.xack.assert_called_once_with(
        KB_INDEX_STATUS_STREAM, cache.xgroup_create.call_args.args[1], '1-0'
    )
    assert (await get_doc(test_session, doc_id)).index_status == 'COMPLETE'


def upload(test_client, auth_token, kb_id):
    return test_client.post(
        f'/floware/v1/knowledge-bases/{kb_id}/documents',
        headers={'Authorization': f'Bearer {auth_token}'},
        files={'file': ('doc.txt', b'some text', 'text/plain')},
    )


async def only_doc_of(test_session, kb_id) -> KnowledgeBaseDocuments:
    async with test_session() as session:
        docs = (
            await session.scalars(
                select(KnowledgeBaseDocuments).where(
                    KnowledgeBaseDocuments.knowledge_base_id == kb_id
                )
            )
        ).all()
    assert len(docs) == 1
    return docs[0]


class TestUploadStatus:
    async def test_queued_document_is_marked_queued(
        self, seeded, test_client, auth_token, test_session
    ):
        kb_id = await create_kb(test_session)

        response = upload(test_client, auth_token, kb_id)

        assert response.status_code == status.HTTP_200_OK
        doc = await only_doc_of(test_session, kb_id)
        assert doc.index_status == 'QUEUED'
        assert doc.index_status_updated_at is None

    async def test_enqueue_failure_marks_document_failed(
        self, seeded, test_client, auth_token, test_session, kb_container
    ):
        kb_container.message_queue().add_message.side_effect = Exception('queue down')
        kb_id = await create_kb(test_session)
        try:
            response = upload(test_client, auth_token, kb_id)
        finally:
            kb_container.message_queue().add_message.side_effect = None

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        doc = await only_doc_of(test_session, kb_id)
        assert doc.index_status == 'FAILED'
        assert 'queue down' in doc.index_error

    async def test_storage_upload_failure_marks_document_failed(
        self, seeded, test_client, auth_token, test_session, kb_container
    ):
        kb_container.cloud_storage().save_small_file.side_effect = Exception(
            'bucket down'
        )
        kb_id = await create_kb(test_session)
        try:
            response = upload(test_client, auth_token, kb_id)
        finally:
            kb_container.cloud_storage().save_small_file.side_effect = None

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        doc = await only_doc_of(test_session, kb_id)
        assert doc.index_status == 'FAILED'
        assert 'bucket down' in doc.index_error

    async def test_document_list_includes_index_status(
        self, seeded, test_client, auth_token, test_session
    ):
        kb_id = await create_kb(test_session)
        upload(test_client, auth_token, kb_id)

        response = test_client.get(
            f'/floware/v1/knowledge-bases/{kb_id}/documents',
            headers={'Authorization': f'Bearer {auth_token}'},
        )

        [resource] = response.json()['data']['resources']
        assert resource['index_status'] == 'QUEUED'
        assert 'index_error' in resource and 'index_status_updated_at' in resource
