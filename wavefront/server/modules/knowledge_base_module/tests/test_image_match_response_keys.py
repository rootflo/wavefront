"""Image search responses name scores by role, not by embedding model.

`primary_score` is the DINO similarity and `secondary_score` the CLIP
similarity. The model names must not appear as response keys, and results
carry no `matched_by` field saying which model surfaced them.
"""

import dataclasses
import uuid
from unittest.mock import AsyncMock, MagicMock

import flo_lib.http as httpx
from knowledge_base_module.queries.generate_query import QueryGenerator
from knowledge_base_module.services.image_rag_retrieve import ImageRagRetrieve

MODEL_NAMES = ('clip', 'dino')


def _assert_no_model_names(payload: dict) -> None:
    assert 'matched_by' not in payload
    for key in payload:
        assert not any(name in key.lower() for name in MODEL_NAMES), key


def _row(doc_id, **scores):
    return {
        'document_id': doc_id,
        'embedding_id': uuid.uuid4(),
        'file_path': f'images/{doc_id}.png',
        'file_name': f'{doc_id}.png',
        'knowledge_base_id': uuid.uuid4(),
        'metadata_value': {},
        **scores,
    }


async def test_union_results_use_primary_and_secondary_scores():
    both, clip_only, dino_only = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    retriever = ImageRagRetrieve(knowledge_base_embeddings_repository=MagicMock())
    retriever.image_retrieve_clip = AsyncMock(
        return_value=[
            _row(both, clip_score=0.6),
            _row(clip_only, clip_score=0.4),
        ]
    )
    retriever.image_retrieve_dino = AsyncMock(
        return_value=[
            _row(both, similarity=0.8),
            _row(dino_only, similarity=0.9),
        ]
    )

    results = await retriever.image_retrieve_clip_dino_union(
        [0.1], [0.2], uuid.uuid4(), 10, ''
    )
    by_id = {match.document_id: dataclasses.asdict(match) for match in results}

    for payload in by_id.values():
        _assert_no_model_names(payload)

    assert by_id[both]['primary_score'] == 0.8
    assert by_id[both]['secondary_score'] == 0.6
    assert by_id[both]['combined_score'] == 0.7

    assert by_id[clip_only]['primary_score'] == 0
    assert by_id[clip_only]['secondary_score'] == 0.4

    assert by_id[dino_only]['primary_score'] == 0.9
    assert by_id[dino_only]['secondary_score'] == 0


def test_exact_match_query_names_score_primary_score():
    sql_query, _ = QueryGenerator().get_image_embedding_dino_exact_match(
        [0.1], str(uuid.uuid4()), None, None, None, 10
    )

    assert 'AS primary_score' in sql_query
    assert 'dino_score' not in sql_query


async def test_exact_match_filters_on_primary_score(monkeypatch):
    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *args, **kwargs):
            response = MagicMock()
            response.json.return_value = {
                'data': {'response': [{'clip': [0.1]}, {'dino': [0.2]}]}
            }
            return response

    monkeypatch.setattr(httpx, 'AsyncClient', FakeClient)

    repository = MagicMock()
    repository.execute_query = AsyncMock(
        return_value=[
            _row(uuid.uuid4(), primary_score=0.95),
            _row(uuid.uuid4(), primary_score=0.5),
        ]
    )
    retriever = ImageRagRetrieve(knowledge_base_embeddings_repository=repository)

    rows = await retriever.exact_match_dino(
        'base64-image', 'http://inference', uuid.uuid4(), None, None, None, 0.8
    )

    assert [row['primary_score'] for row in rows] == [0.95]
    for row in rows:
        _assert_no_model_names(row)


async def test_union_scores_are_rounded_after_ranking():
    higher, lower = uuid.uuid4(), uuid.uuid4()
    retriever = ImageRagRetrieve(knowledge_base_embeddings_repository=MagicMock())
    # Both round to 0.81 on every score, but `higher` is ahead at full
    # precision and must stay first.
    retriever.image_retrieve_clip = AsyncMock(
        return_value=[
            _row(lower, clip_score=0.812341),
            _row(higher, clip_score=0.812349),
        ]
    )
    retriever.image_retrieve_dino = AsyncMock(
        return_value=[
            _row(lower, similarity=0.806661),
            _row(higher, similarity=0.806669),
        ]
    )

    results = await retriever.image_retrieve_clip_dino_union(
        [0.1], [0.2], uuid.uuid4(), 10, ''
    )

    assert [match.document_id for match in results] == [higher, lower]
    for match in results:
        assert match.secondary_score == 0.81
        assert match.primary_score == 0.81
        assert match.combined_score == 0.81
        assert match.similarity == 0.81


async def test_exact_match_thresholds_before_rounding(monkeypatch):
    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *args, **kwargs):
            response = MagicMock()
            response.json.return_value = {'data': {'response': [{'dino': [0.2]}]}}
            return response

    monkeypatch.setattr(httpx, 'AsyncClient', FakeClient)

    repository = MagicMock()
    repository.execute_query = AsyncMock(
        return_value=[
            # Rounds to 0.8 but is below the threshold: must be dropped.
            _row(uuid.uuid4(), primary_score=0.7999),
            _row(uuid.uuid4(), primary_score=0.876543),
        ]
    )
    retriever = ImageRagRetrieve(knowledge_base_embeddings_repository=repository)

    rows = await retriever.exact_match_dino(
        'base64-image', 'http://inference', uuid.uuid4(), None, None, None, 0.8
    )

    assert [row['primary_score'] for row in rows] == [0.88]
