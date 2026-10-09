"""
Tests for floware's query embedding client (BGE-M3 via the inference app), its
use in KBRagResponse, and the hybrid dense + sparse search SQL. The inference
app is an httpx MockTransport; the database is a mock.
"""

import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import flo_lib.http as httpx
import pytest
from knowledge_base_module.embeddings import embed
from knowledge_base_module.embeddings.embed import EmbeddingFunc, TextEmbeddingError
from knowledge_base_module.queries.generate_query import QueryGenerator
from knowledge_base_module.services.kb_rag_retrieve import KBRagResponse

DENSE = [0.1, 0.2, 0.3]
SPARSE = {'indices': [0, 9], 'values': [0.5, 0.1]}


def inference_app(handler):
    """Route EmbeddingFunc's httpx.AsyncClient to `handler`."""
    real_client = httpx.AsyncClient

    def client_factory(**kwargs):
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    return client_factory


def ok(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    return httpx.Response(
        200,
        json={
            'meta': {'status': 'success'},
            'data': {
                'model': 'bge-m3',
                'response': [{'dense': DENSE, 'sparse': SPARSE} for _ in body['texts']],
            },
        },
    )


async def test_embeds_the_query_dense_and_sparse_with_bge_m3(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        return ok(request)

    monkeypatch.setattr(embed.httpx, 'AsyncClient', inference_app(handler))

    embedding = await EmbeddingFunc('http://inference:8003/').embed_query(
        'where is it?'
    )

    assert embedding == {'dense': DENSE, 'sparse': SPARSE}
    [request] = requests
    assert (
        str(request.url) == 'http://inference:8003/inference/v1/query/text-embeddings'
    )
    assert json.loads(request.content) == {
        'texts': ['where is it?'],
        'return_dense': True,
        'return_sparse': True,
    }
    assert 'authorization' not in request.headers


@pytest.mark.parametrize(
    ('handler', 'message'),
    [
        (
            lambda r: httpx.Response(503, text='Text embedding model is still loading'),
            '503',
        ),
        (lambda r: httpx.Response(200, json={'data': {'response': []}}), 'Unexpected'),
        (
            lambda r: httpx.Response(
                200, json={'data': {'response': [{'dense': [1.0]}]}}
            ),
            'Unexpected',
        ),
        (
            lambda r: httpx.Response(
                200, json={'data': {'response': [{'sparse': {}}]}}
            ),
            'Unexpected',
        ),
    ],
)
async def test_bad_responses_raise_a_clear_error(monkeypatch, handler, message):
    monkeypatch.setattr(embed.httpx, 'AsyncClient', inference_app(handler))

    with pytest.raises(TextEmbeddingError, match=message):
        await EmbeddingFunc('http://inference:8003').embed_query('q')


async def test_unreachable_service_raises_a_clear_error(monkeypatch):
    def handler(request):
        raise httpx.ConnectError('connection refused')

    monkeypatch.setattr(embed.httpx, 'AsyncClient', inference_app(handler))

    with pytest.raises(TextEmbeddingError, match='Could not reach'):
        await EmbeddingFunc('http://inference:8003').embed_query('q')


def make_retrieval(monkeypatch):
    monkeypatch.setattr(embed.httpx, 'AsyncClient', inference_app(ok))
    embeddings_repo = MagicMock()
    embeddings_repo.execute_query = AsyncMock(return_value=[{'chunk_text': 'hit'}])
    retrieval = KBRagResponse(
        MagicMock(), embeddings_repo, inference_url='http://inference:8003'
    )
    return retrieval, embeddings_repo


async def test_retrieval_searches_with_the_bge_m3_dense_and_sparse_vectors(monkeypatch):
    retrieval, embeddings_repo = make_retrieval(monkeypatch)

    docs = await retrieval.retrieve_documents('where is it?', uuid4())

    assert docs == [{'chunk_text': 'hit'}]
    _sql, params = embeddings_repo.execute_query.call_args.args
    assert params['query_embed'] == str(DENSE)
    # pgvector's sparsevec text form is 1-based: token ids 0 and 9 -> 1 and 10
    assert params['query_sparse'] == '{1:0.5,10:0.1}/250002'
    assert (params['threshold'], params['vector_weight'], params['keyword_weight']) == (
        0.2,
        0.7,
        0.3,
    )


async def test_zero_threshold_and_weights_are_honoured(monkeypatch):
    # These used to be `x or default`, so 0 silently became the default.
    retrieval, embeddings_repo = make_retrieval(monkeypatch)

    await retrieval.retrieve_documents(
        'q', uuid4(), threshold=0, vector_weight=0, keyword_weight=1
    )

    _sql, params = embeddings_repo.execute_query.call_args.args
    assert (params['threshold'], params['vector_weight'], params['keyword_weight']) == (
        0.0,
        0.0,
        1.0,
    )


def hybrid_sql(**kwargs):
    return QueryGenerator().get_combined_search_query(
        DENSE, SPARSE, {'kb_id': uuid4()}, filter='', **kwargs
    )


def test_hybrid_search_uses_bge_m3_dense_and_sparse_indexes():
    sql, _ = hybrid_sql()

    # candidate searches ORDER BY the bare columns, so their HNSW indexes apply
    assert 'ORDER BY e.text_embedding <=> :query_embed ::vector(1024)' in sql
    assert (
        'ORDER BY e.text_sparse_embedding <#> :query_sparse ::sparsevec(250002)' in sql
    )
    assert 'vector(512)' not in sql


def test_every_candidate_is_scored_on_both_dense_and_sparse():
    sql, _ = hybrid_sql()

    # scores are computed per candidate, not COALESCEd from one side of a join
    assert (
        '1 - (e.text_embedding <=> :query_embed ::vector(1024)) AS vector_score' in sql
    )
    assert (
        'COALESCE(-(e.text_sparse_embedding <#> :query_sparse ::sparsevec(250002)), 0) '
        'AS text_score'
    ) in sql
    assert 'FULL OUTER JOIN' not in sql


def test_english_tsvector_keyword_search_is_gone():
    sql, params = hybrid_sql()

    for removed in (
        'ts_rank',
        'plainto_tsquery',
        'to_tsvector',
        "'english'",
        'e.token',
    ):
        assert removed not in sql
    assert 'query' not in params


def test_filters_apply_to_both_candidate_searches():
    sql, params = hybrid_sql(filter1='branch-7')

    assert sql.count('d.knowledge_base_id = :kb_id') == 2
    assert sql.count('d.filter1 = :filter1') == 2
    assert params['filter1'] == 'branch-7'


@pytest.mark.parametrize(
    ('limit', 'offset', 'expected'), [(10, None, 100), (5, 0, 100), (20, 10, 300)]
)
def test_candidate_pool_covers_the_requested_page(limit, offset, expected):
    _, params = hybrid_sql(limit=limit, offset=offset)

    assert params['candidate_limit'] == expected


def test_empty_sparse_query_still_searches_dense():
    _, params = QueryGenerator().get_combined_search_query(
        DENSE, {'indices': [], 'values': []}, {'kb_id': uuid4()}, filter=''
    )

    assert params['query_sparse'] == '{}/250002'


# --- item 9: ef_search / iterative scan for text search ---------------------


@pytest.mark.parametrize(('limit', 'expected_ef_search'), [(None, 400), (30, 1000)])
async def test_text_search_raises_ef_search_and_enables_iterative_scan(
    monkeypatch, limit, expected_ef_search
):
    retrieval, embeddings_repo = make_retrieval(monkeypatch)

    await retrieval.retrieve_documents('q', uuid4(), limit=limit)

    # execute_query applies SET LOCAL hnsw.ef_search and
    # hnsw.iterative_scan = relaxed_order whenever ef_search is passed.
    # ef_search = candidate_limit x 4, floored at 200 and capped at 1000:
    # limit 10 -> 100 candidates -> 400; limit 30 -> 300 -> 1000 (cap).
    assert embeddings_repo.execute_query.call_args.kwargs['ef_search'] == (
        expected_ef_search
    )


# --- item 10: TextEmbeddingError carries the inference status ---------------


@pytest.mark.parametrize(
    ('status_code', 'retryable'), [(503, True), (429, True), (500, False), (413, False)]
)
async def test_error_carries_status_and_retryability(
    monkeypatch, status_code, retryable
):
    monkeypatch.setattr(
        embed.httpx,
        'AsyncClient',
        inference_app(lambda r: httpx.Response(status_code, text='nope')),
    )

    with pytest.raises(TextEmbeddingError) as raised:
        await EmbeddingFunc('http://inference:8003').embed_query('q')

    assert raised.value.status_code == status_code
    assert raised.value.retryable is retryable


async def test_unreachable_service_is_not_retryable(monkeypatch):
    def handler(request):
        raise httpx.ConnectError('connection refused')

    monkeypatch.setattr(embed.httpx, 'AsyncClient', inference_app(handler))

    with pytest.raises(TextEmbeddingError) as raised:
        await EmbeddingFunc('http://inference:8003').embed_query('q')

    assert raised.value.status_code is None and not raised.value.retryable
