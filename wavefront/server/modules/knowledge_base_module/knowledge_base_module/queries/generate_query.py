import re
from typing import Any, Dict, List, Optional, Tuple

from db_repo_module.models.knowledge_base_documents import KnowledgeBaseDocuments
from db_repo_module.models.knowledge_base_embeddings import (
    TEXT_EMBEDDING_DIM,
    TEXT_SPARSE_EMBEDDING_DIM,
    KnowledgeBaseEmbeddings,
)
from pgvector import SparseVector
from datasource.odata_parser import ODataQueryParser
from datasource.dialect import PostgresSqlDialect


class QueryGenerator:
    """Class to generate SQL queries for knowledge base operations."""

    def __init__(self):
        self.odata_parser = ODataQueryParser(
            type='sql',
            dynamic_var_char=':',
            dialect=PostgresSqlDialect(),
        )

    def build_metadata_clause(
        self,
        template: str,
        filter_params: Dict[str, Any],
        formatter,
    ) -> str:
        clause = template
        for field in filter_params.keys():
            pattern = rf'(?<!:)\b{re.escape(field)}\b'
            clause = re.sub(pattern, formatter(field), clause)
        return clause

    def build_filter_columns_clause(
        self,
        filter1: Optional[str] = None,
        filter2: Optional[str] = None,
        filter3: Optional[str] = None,
        filter4: Optional[str] = None,
        filter5: Optional[str] = None,
        filter6: Optional[str] = None,
        document_date_start: Optional[Any] = None,
        document_date_end: Optional[Any] = None,
        table_alias: str = 'd',
        created_at_start: Optional[Any] = None,
        created_at_end: Optional[Any] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Build an `AND ...` SQL fragment (empty string if nothing is set) plus
        matching bind params for the real, indexed `filter1`..`filter6`,
        `document_date`, and `created_at` columns on
        `knowledge_base_documents`. Shared by every query that joins that
        table in under `table_alias`, so filtering on these columns behaves
        the same regardless of retrieval mode (hybrid text search, image ANN
        search, or the DINO exact match) rather than being special-cased to
        one of them.

        `document_date`/`created_at` are only filtered when both the
        matching `_start` and `_end` are given -- a one-sided window isn't
        supported by the underlying `BETWEEN`.
        """
        params: Dict[str, Any] = {}
        clauses = []
        for name, value in (
            ('filter1', filter1),
            ('filter2', filter2),
            ('filter3', filter3),
            ('filter4', filter4),
            ('filter5', filter5),
            ('filter6', filter6),
        ):
            if value is not None:
                params[name] = value
                clauses.append(f'AND {table_alias}.{name} = :{name}')
        if document_date_start is not None and document_date_end is not None:
            params['document_date_start'] = document_date_start
            params['document_date_end'] = document_date_end
            clauses.append(
                f'AND {table_alias}.document_date BETWEEN '
                ':document_date_start AND :document_date_end'
            )
        if created_at_start is not None and created_at_end is not None:
            params['created_at_start'] = created_at_start
            params['created_at_end'] = created_at_end
            clauses.append(
                f'AND {table_alias}.created_at BETWEEN '
                ':created_at_start AND :created_at_end'
            )
        return ' '.join(clauses), params

    def compute_ef_search(
        self,
        effective_limit: int,
        safety_factor: int = 4,
        floor: int = 200,
        ceiling: int = 1000,
    ) -> int:
        """
        Compute a safe value for the pgvector session parameter `hnsw.ef_search`.

        `ef_search` caps how many candidates the HNSW index can return for a
        given query, regardless of the SQL `LIMIT` (it defaults to 40 if never
        set). It must be at least as large as the number of rows a query
        needs, or results silently come back short. We scale it off the
        requested limit with headroom, floor it at a value known to give
        ~97-99% recall on real embeddings, and cap it at pgvector's hard
        maximum (1000).
        """
        return max(min(effective_limit * safety_factor, ceiling), floor)

    def get_combined_search_query(
        self,
        query_dense: List[float],
        query_sparse: Dict[str, List],
        params: Dict[str, Any],
        filter: str,
        offset: Optional[int] = None,
        limit: Optional[int] = None,
        filter1: Optional[str] = None,
        filter2: Optional[str] = None,
        filter3: Optional[str] = None,
        filter4: Optional[str] = None,
        filter5: Optional[str] = None,
        filter6: Optional[str] = None,
        document_date_start: Optional[Any] = None,
        document_date_end: Optional[Any] = None,
        created_at_start: Optional[Any] = None,
        created_at_end: Optional[Any] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Hybrid text search over BGE-M3 dense and sparse (lexical) vectors.

        Candidates are the nearest chunks by dense cosine distance and by
        sparse inner product, each from its own HNSW index and within the KB
        and filters. Every candidate is then scored on both, from the same
        model, so the scores are on comparable scales:

            vector_score   = cosine similarity of the dense vectors
            text_score     = inner product of the sparse (lexical) vectors
            combined_score = vector_weight * vector_score
                             + keyword_weight * text_score

        This is BGE-M3's own dense + sparse hybrid. It replaces the English
        tsvector keyword search, whose unbounded ts_rank_cd scores were not
        comparable with cosine similarity and only matched English.

        Args:
            query_dense: The query's BGE-M3 dense vector
            query_sparse: The query's BGE-M3 sparse vector, {indices, values}
            params: threshold (on combined_score), vector_weight,
                keyword_weight, top_k, kb_id

        Returns:
            Tuple of (SQL query string, query parameters)
        """
        threshold = float(params.get('threshold', 0.2))
        effective_limit = limit if limit is not None else int(params.get('top_k', 10))
        vector_weight = float(params.get('vector_weight', 0.7))
        keyword_weight = float(params.get('keyword_weight', 0.3))
        kb_id = str(params.get('kb_id'))
        effective_offset = offset or 0
        # Per index, enough candidates that the page asked for can still be
        # filled after the two sets are merged and thresholded.
        candidate_limit = max((effective_limit + effective_offset) * 10, 100)

        query_params = {
            'query_embed': str(list(query_dense)),
            'query_sparse': _sparse_text(query_sparse),
            'threshold': threshold,
            'kb_id': kb_id,
            'vector_weight': vector_weight,
            'keyword_weight': keyword_weight,
            'offset': effective_offset,
            'limit': effective_limit,
            'candidate_limit': candidate_limit,
        }
        metadata_filter_clause = ''
        if filter:
            where_clause, filter_params = self.odata_parser.prepare_odata_filter(filter)
            if where_clause and filter_params:
                metadata_filter_clause = self.build_metadata_clause(
                    where_clause,
                    filter_params,
                    lambda field: f"(d.metadata_value ->> '{field}')",
                )
                query_params.update(filter_params)

        filter_columns_clause, filter_columns_params = self.build_filter_columns_clause(
            filter1,
            filter2,
            filter3,
            filter4,
            filter5,
            filter6,
            document_date_start,
            document_date_end,
            table_alias='d',
            created_at_start=created_at_start,
            created_at_end=created_at_end,
        )
        query_params.update(filter_columns_params)

        scope = (
            'd.knowledge_base_id = :kb_id'
            + (f' AND ({metadata_filter_clause})' if metadata_filter_clause else '')
            + f' {filter_columns_clause}'
        )
        dense = f':query_embed ::vector({TEXT_EMBEDDING_DIM})'
        sparse = f':query_sparse ::sparsevec({TEXT_SPARSE_EMBEDDING_DIM})'
        embeddings = KnowledgeBaseEmbeddings.__tablename__
        documents = KnowledgeBaseDocuments.__tablename__

        # ORDER BY the bare columns (no casts) so each HNSW index applies:
        # ix_kbe_text_embedding_hnsw_cosine and ix_kbe_text_sparse_embedding_hnsw_ip.
        sql_query = f"""
            WITH dense_candidates AS (
                SELECT e.id
                FROM {embeddings} e
                JOIN {documents} d ON e.document_id = d.id
                WHERE {scope}
                    AND e.text_embedding IS NOT NULL
                ORDER BY e.text_embedding <=> {dense}
                LIMIT :candidate_limit
            ),
            sparse_candidates AS (
                SELECT e.id
                FROM {embeddings} e
                JOIN {documents} d ON e.document_id = d.id
                WHERE {scope}
                    AND e.text_sparse_embedding IS NOT NULL
                ORDER BY e.text_sparse_embedding <#> {sparse}
                LIMIT :candidate_limit
            ),
            scored AS (
                SELECT
                    e.id AS embedding_id,
                    e.chunk_text,
                    e.chunk_index,
                    d.id AS document_id,
                    d.file_path,
                    d.metadata_value,
                    d.knowledge_base_id,
                    1 - (e.text_embedding <=> {dense}) AS vector_score,
                    -- <#> is the negative inner product
                    COALESCE(-(e.text_sparse_embedding <#> {sparse}), 0) AS text_score
                FROM {embeddings} e
                JOIN {documents} d ON e.document_id = d.id
                WHERE e.id IN (
                    SELECT id FROM dense_candidates
                    UNION
                    SELECT id FROM sparse_candidates
                )
            )
            SELECT
                embedding_id,
                chunk_text,
                chunk_index,
                document_id,
                file_path,
                metadata_value,
                knowledge_base_id,
                vector_score * :vector_weight + text_score * :keyword_weight
                    AS combined_score,
                vector_score,
                text_score
            FROM scored
            WHERE vector_score * :vector_weight + text_score * :keyword_weight
                > :threshold
            ORDER BY combined_score DESC
            LIMIT :limit OFFSET :offset
        """

        return sql_query, query_params

    def get_image_embedding_clip(
        self, query_embeddings: list, params: Dict[str, Any], filter: str
    ):
        kb_id = str(params.get('kb_id'))
        top_k = int(params.get('top_k', 10))
        filter_columns_clause, filter_columns_params = self.build_filter_columns_clause(
            params.get('filter1'),
            params.get('filter2'),
            params.get('filter3'),
            params.get('filter4'),
            params.get('filter5'),
            params.get('filter6'),
            params.get('document_date_start'),
            params.get('document_date_end'),
            table_alias='d',
            created_at_start=params.get('created_at_start'),
            created_at_end=params.get('created_at_end'),
        )

        # Prepare query parameters
        params = {
            'query_embedding': query_embeddings,
            'kb_id': kb_id,
            'top_k': top_k,
            **filter_columns_params,
        }
        metadata_filter_clause = ''
        if filter:
            where_clause, filter_params = self.odata_parser.prepare_odata_filter(filter)
            if where_clause and filter_params:
                metadata_filter_clause = self.build_metadata_clause(
                    where_clause,
                    filter_params,
                    lambda field: f"(d.metadata_value ->> '{field}')",
                )
                params.update(filter_params)
        # NOTE: the filter (WHERE d.knowledge_base_id = :kb_id) and the
        # distance ORDER BY/LIMIT are kept in the same query scope on
        # purpose, so Postgres's planner can choose per-query whether to
        # brute-force a small/highly-selective KB or use the HNSW index for
        # a large one, instead of always being forced through the index via
        # an unfiltered candidate CTE.
        sql_query = f"""
        SELECT
            e.id AS embedding_id,
            d.id AS document_id,
            d.file_path,
            d.file_name,
            d.knowledge_base_id,
            d.metadata_value,
            (e.embedding_vector::vector(512)) <=> :query_embedding ::vector(512) AS distance,
            1 - ((e.embedding_vector::vector(512)) <=> :query_embedding ::vector(512)) AS clip_score
        FROM {KnowledgeBaseEmbeddings.__tablename__} e
        JOIN {KnowledgeBaseDocuments.__tablename__} d ON e.document_id = d.id
        WHERE d.knowledge_base_id = :kb_id
            {'AND (' + metadata_filter_clause + ')' if metadata_filter_clause else ''} {filter_columns_clause}
        ORDER BY (e.embedding_vector::vector(512)) <=> :query_embedding ::vector(512)
        LIMIT :top_k
        """

        return sql_query, params

    def get_image_embedding_dino(
        self, query_embeddings: list, params: Dict[str, Any], filter: str
    ):
        kb_id = str(params.get('kb_id'))
        top_k = int(params.get('top_k', 10))
        filter_columns_clause, filter_columns_params = self.build_filter_columns_clause(
            params.get('filter1'),
            params.get('filter2'),
            params.get('filter3'),
            params.get('filter4'),
            params.get('filter5'),
            params.get('filter6'),
            params.get('document_date_start'),
            params.get('document_date_end'),
            table_alias='d',
            created_at_start=params.get('created_at_start'),
            created_at_end=params.get('created_at_end'),
        )

        params = {
            'query_embedding': query_embeddings,
            'kb_id': kb_id,
            'top_k': top_k,
            **filter_columns_params,
        }

        metadata_filter_clause = ''
        if filter:
            where_clause, filter_params = self.odata_parser.prepare_odata_filter(filter)
            if where_clause and filter_params:
                metadata_filter_clause = self.build_metadata_clause(
                    where_clause,
                    filter_params,
                    lambda field: f"(d.metadata_value ->> '{field}')",
                )
                params.update(filter_params)

        # NOTE: same reasoning as get_image_embedding_clip -- filter and
        # ORDER BY/LIMIT share the same query scope so Postgres's planner
        # can brute-force small/highly-selective KBs instead of always
        # going through the HNSW index via an unfiltered candidate CTE.
        #
        # NOTE: ORDER BY deliberately repeats the raw `<=>` distance
        # expression (ascending) rather than sorting by the `similarity`
        # alias descending. The two are mathematically equivalent (since
        # similarity = 1 - distance), but the HNSW index
        # (ix_kbe_embedding_vector_1_hnsw_cosine) can only be used to
        # satisfy an ORDER BY that matches its indexed `<=>` expression
        # literally -- sorting by a derived alias like `similarity DESC`
        # is invisible to the planner and forces a full scan + explicit
        # sort instead.
        sql_query = f"""
        SELECT
            e.id AS embedding_id,
            d.id AS document_id,
            d.file_path,
            d.file_name,
            d.knowledge_base_id,
            d.metadata_value,
            1 - ((e.embedding_vector_1::vector(1024)) <=> :query_embedding ::vector(1024)) AS similarity
        FROM {KnowledgeBaseEmbeddings.__tablename__} e
        JOIN {KnowledgeBaseDocuments.__tablename__} d ON e.document_id = d.id
        WHERE d.knowledge_base_id = :kb_id
            {'AND (' + metadata_filter_clause + ')' if metadata_filter_clause else ''} {filter_columns_clause}
        ORDER BY (e.embedding_vector_1::vector(1024)) <=> :query_embedding ::vector(1024)
        LIMIT :top_k
        """

        return sql_query, params

    def get_image_embedding_dino_exact_match(
        self,
        query_embeddings: list,
        kb_id: str,
        filter1: Optional[str],
        document_date_start,
        document_date_end,
        max_candidates: int,
        filter2: Optional[str] = None,
        filter3: Optional[str] = None,
        filter4: Optional[str] = None,
        filter5: Optional[str] = None,
        filter6: Optional[str] = None,
        created_at_start: Optional[Any] = None,
        created_at_end: Optional[Any] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Exact (brute-force) DINO similarity search over documents in a KB,
        optionally narrowed by `filter1`..`filter6` and a `document_date` /
        `created_at` window. All `filterN` columns are generic, caller-defined
        columns -- see `KnowledgeBaseDocuments` -- this query has no notion of
        what they mean semantically.

        Candidates are capped via `ORDER BY d.id LIMIT :fetch_limit`, where
        `fetch_limit` is computed here as `max_candidates + 1`. Ordering by
        `d.id` -- a plain, non-vector column -- rather than the `<=>`
        distance expression keeps this from ever engaging the HNSW index
        (`ix_kbe_embedding_vector_1_hnsw_cosine`), which only gets used when
        `ORDER BY`/`LIMIT` is tied directly to a `<=>` expression. That means
        results here stay exact, not approximate, for whatever candidate set
        the `LIMIT` lets through. The "+1" lets the caller detect when the
        true candidate count exceeded `max_candidates` (i.e.
        `len(rows) == max_candidates + 1`) without a separate `COUNT` query.

        Deliberately has no `dino_score` threshold filter in this query --
        that comparison is left to the caller so it can distinguish "no
        candidates matched" from "the candidate set was truncated" using the
        raw (pre-threshold) row count returned here.
        """
        filter_columns_clause, filter_columns_params = self.build_filter_columns_clause(
            filter1,
            filter2,
            filter3,
            filter4,
            filter5,
            filter6,
            document_date_start,
            document_date_end,
            table_alias='d',
            created_at_start=created_at_start,
            created_at_end=created_at_end,
        )

        params: Dict[str, Any] = {
            'query_embedding': query_embeddings,
            'kb_id': str(kb_id),
            'fetch_limit': max_candidates + 1,
            **filter_columns_params,
        }

        sql_query = f"""
        SELECT
            e.id AS embedding_id,
            d.id AS document_id,
            d.file_path,
            d.file_name,
            d.knowledge_base_id,
            d.metadata_value,
            d.document_date::text AS document_date,
            1 - ((e.embedding_vector_1::vector(1024)) <=> :query_embedding ::vector(1024)) AS dino_score
        FROM {KnowledgeBaseEmbeddings.__tablename__} e
        JOIN {KnowledgeBaseDocuments.__tablename__} d ON e.document_id = d.id
        WHERE d.knowledge_base_id = :kb_id
            {filter_columns_clause}
        ORDER BY d.id
        LIMIT :fetch_limit
        """

        return sql_query, params

    def get_documents_list_query(
        self,
        kb_id: str,
        file_type: Optional[str] = None,
        filter: Optional[str] = None,
        offset: int = 0,
        limit: int = 10,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Generate SQL query to list knowledge base documents with optional
        metadata filter (OData-style $filter) and file_type.

        Returns:
            Tuple of (SQL query string, query parameters)
        """
        params: Dict[str, Any] = {
            'kb_id': kb_id,
            'offset': offset,
            'limit': limit,
        }
        conditions = ['knowledge_base_id = :kb_id']
        if file_type:
            params['file_type'] = file_type
            conditions.append('file_type = :file_type')

        metadata_filter_clause = ''
        if filter:
            where_clause, filter_params = self.odata_parser.prepare_odata_filter(filter)
            if where_clause and filter_params:
                metadata_filter_clause = self.build_metadata_clause(
                    where_clause,
                    filter_params,
                    lambda field: f"(metadata_value ->> '{field}')",
                )
                params.update(filter_params)
                conditions.append(f'({metadata_filter_clause})')

        where_sql = ' AND '.join(conditions)
        sql_query = f"""
            SELECT
                id,
                knowledge_base_id,
                file_path,
                file_name,
                file_type,
                file_size,
                created_at,
                updated_at,
                metadata_value,
                index_status,
                index_error,
                index_status_updated_at
            FROM
                {KnowledgeBaseDocuments.__tablename__}
            WHERE
                {where_sql}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """
        return sql_query, params


def _sparse_text(sparse: Optional[Dict[str, List]]) -> str:
    """BGE-M3 {indices, values} (0-based token ids) in pgvector's sparsevec
    text form. An empty vector scores 0 against every chunk."""
    sparse = sparse or {}
    weights = dict(zip(sparse.get('indices', []), sparse.get('values', [])))
    return SparseVector(weights, TEXT_SPARSE_EMBEDDING_DIM).to_text()
