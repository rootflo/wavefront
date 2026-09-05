import re
from typing import Any, Dict, Tuple, Optional

from db_repo_module.models.knowledge_base_documents import KnowledgeBaseDocuments
from db_repo_module.models.knowledge_base_embeddings import KnowledgeBaseEmbeddings
from datasource.odata_parser import ODataQueryParser


class QueryGenerator:
    """Class to generate SQL queries for knowledge base operations."""

    def __init__(self):
        self.odata_parser = ODataQueryParser(type='sql', dynamic_var_char=':')

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
        query: str,
        query_embeddings: list,
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
        Generate SQL query for combined vector and keyword search with reranking.

        Args:
            query: The search query text
            query_embeddings: The vector embeddings of the query
            params: Dictionary containing query parameters:
                - threshold: Cosine similarity threshold
                - top_k: Number of results to return
                - vector_weight: Weight for vector similarity score
                - keyword_weight: Weight for keyword similarity score
                - kb_id: Knowledge base ID

        Returns:
            Tuple of (SQL query string, query parameters)
        """
        # Validate and sanitize parameters
        threshold = float(params.get('threshold', 0.2))
        # Use limit if provided, otherwise use top_k
        effective_limit = limit if limit is not None else int(params.get('top_k', 10))
        vector_weight = float(params.get('vector_weight', 0.7))
        keyword_weight = float(params.get('keyword_weight', 0.3))
        kb_id = str(params.get('kb_id'))
        effective_offset = offset or 0

        # Prepare query parameters
        query_params = {
            'query_embed': str(query_embeddings[0]),
            'threshold': threshold,
            'kb_id': kb_id,
            'vector_weight': vector_weight,
            'keyword_weight': keyword_weight,
            'query': query,
            'offset': effective_offset,
            'limit': effective_limit,
        }
        metadata_filter_clause_final = ''
        metadata_filter_clause_inner = ''
        if filter:
            where_clause, filter_params = self.odata_parser.prepare_odata_filter(filter)
            if where_clause and filter_params:
                metadata_filter_clause_final = self.build_metadata_clause(
                    where_clause,
                    filter_params,
                    lambda field: (
                        f"(COALESCE(k.metadata_value ->> '{field}', "
                        f"v.metadata_value ->> '{field}'))"
                    ),
                )
                metadata_filter_clause_inner = self.build_metadata_clause(
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

        sql_query = f"""
            WITH hnsw_candidates AS (
                SELECT
                    e.id,
                    e.document_id,
                    e.chunk_text,
                    e.chunk_index,
                    d.file_path,
                    d.knowledge_base_id,
                    d.metadata_value,
                    (e.embedding_vector::vector(512)) <=> :query_embed ::vector(512) AS distance
                FROM
                    {KnowledgeBaseEmbeddings.__tablename__} e
                JOIN
                    {KnowledgeBaseDocuments.__tablename__} d ON e.document_id = d.id
                WHERE
                     d.knowledge_base_id = :kb_id {'AND (' + metadata_filter_clause_inner + ')' if metadata_filter_clause_inner else ''} {filter_columns_clause}
                ORDER BY
                    (e.embedding_vector::vector(512)) <=> :query_embed ::vector(512)
                LIMIT :limit * 20
            ),
            vector_results AS (
                SELECT
                    id as embedding_id,
                    chunk_text,
                    chunk_index,
                    document_id,
                    file_path,
                    knowledge_base_id,
                    metadata_value,
                    1 - distance as vector_score
                FROM
                    hnsw_candidates
                ORDER BY
                    distance ASC
                LIMIT :limit
            ),
            keyword_results AS (
                SELECT
                    e.id as embedding_id,
                    e.chunk_text,
                    e.chunk_index,
                    d.id as document_id,
                    d.file_path,
                    d.knowledge_base_id,
                    d.metadata_value,
                    ts_rank_cd(e.token, query_tokens) AS text_score
                FROM
                    {KnowledgeBaseEmbeddings.__tablename__} e
                JOIN
                    {KnowledgeBaseDocuments.__tablename__} d ON e.document_id = d.id,
                    plainto_tsquery('english', :query) AS query_tokens
                WHERE
                    e.token @@ query_tokens
                    AND d.knowledge_base_id = :kb_id {'AND (' + metadata_filter_clause_inner + ')' if metadata_filter_clause_inner else ''} {filter_columns_clause}
                ORDER BY
                    text_score DESC
                LIMIT :limit
            )
            SELECT
                COALESCE(k.embedding_id, v.embedding_id) as embedding_id,
                COALESCE(k.chunk_text, v.chunk_text) as chunk_text,
                COALESCE(k.chunk_index, v.chunk_index) as chunk_index,
                COALESCE(k.document_id, v.document_id) as document_id,
                COALESCE(k.file_path, v.file_path) as file_path,
                COALESCE(k.metadata_value, v.metadata_value) as metadata_value,
                COALESCE(k.knowledge_base_id, v.knowledge_base_id) as knowledge_base_id,
                COALESCE(v.vector_score, 0) * :vector_weight +
                COALESCE(k.text_score, 0) * :keyword_weight AS combined_score,
                COALESCE(v.vector_score, 0) as vector_score,
                COALESCE(k.text_score, 0) as text_score
            FROM
                keyword_results k
            FULL OUTER JOIN
                vector_results v ON k.embedding_id = v.embedding_id
            WHERE
              (COALESCE(v.vector_score, 0) * :vector_weight +
               COALESCE(k.text_score, 0) * :keyword_weight) > :threshold {'AND (' + metadata_filter_clause_final + ')' if metadata_filter_clause_final else ''}
            ORDER BY
                combined_score DESC
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
        filter1: str,
        document_date_start,
        document_date_end,
        threshold: float,
        filter2: Optional[str] = None,
        filter3: Optional[str] = None,
        filter4: Optional[str] = None,
        filter5: Optional[str] = None,
        filter6: Optional[str] = None,
        created_at_start: Optional[Any] = None,
        created_at_end: Optional[Any] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Exact (brute-force) DINO similarity search restricted to documents on
        `knowledge_base_documents` matching `filter1` and a `document_date`
        window, further narrowed by an equality match on any of
        `filter2`..`filter6` that are provided. All `filterN` columns are
        generic, caller-defined columns -- see `KnowledgeBaseDocuments` --
        this query has no notion of what they mean semantically.

        Deliberately has no `ORDER BY`/`LIMIT` tied to the `<=>` distance
        expression anywhere -- that is what would let Postgres route the
        query through the HNSW index (`ix_kbe_embedding_vector_1_hnsw_cosine`)
        for an *approximate* top-K search. Here we instead pre-filter to a
        small candidate set via the real, indexed `filterN`/`document_date`
        columns, then compute an exact cosine distance for every one of those
        rows and only keep the ones above `threshold` -- so results are exact,
        not approximate, and the count of matches is precise.

        The threshold check is a plain scalar comparison on the computed
        `dino_score`, so it has to live in an outer query over a subquery
        (Postgres doesn't allow referencing a `SELECT`-list alias in a
        same-level `WHERE`) -- it still runs after every distance in the
        candidate set has already been computed exactly.
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
            'threshold': threshold,
            **filter_columns_params,
        }

        sql_query = f"""
        SELECT * FROM (
            SELECT
                e.id AS embedding_id,
                d.id AS document_id,
                d.file_path,
                d.file_name,
                d.knowledge_base_id,
                d.metadata_value,
                1 - ((e.embedding_vector_1::vector(1024)) <=> :query_embedding ::vector(1024)) AS dino_score
            FROM {KnowledgeBaseEmbeddings.__tablename__} e
            JOIN {KnowledgeBaseDocuments.__tablename__} d ON e.document_id = d.id
            WHERE d.knowledge_base_id = :kb_id
                {filter_columns_clause}
        ) scored
        WHERE dino_score > :threshold
        """

        return sql_query, params

    def get_filtered_document_count_query(
        self,
        kb_id: str,
        filter1: Optional[str] = None,
        document_date_start: Optional[Any] = None,
        document_date_end: Optional[Any] = None,
        filter2: Optional[str] = None,
        filter3: Optional[str] = None,
        filter4: Optional[str] = None,
        filter5: Optional[str] = None,
        filter6: Optional[str] = None,
        created_at_start: Optional[Any] = None,
        created_at_end: Optional[Any] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Cheap, index-only count of documents in `kb_id` matching the same
        `filterN`/`document_date`/`created_at` window used by
        `get_image_embedding_dino_exact_match`. Intended as a pre-flight
        safety check -- callers should run this first and compare the
        result against a candidate-count cap before running the (much more
        expensive) exact-match brute-force distance computation, since this
        query only touches the real, indexed columns on
        `knowledge_base_documents` and never reads `knowledge_base_embeddings`
        or computes any vector distance.
        """
        filter_columns_clause, params = self.build_filter_columns_clause(
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
        params['kb_id'] = str(kb_id)

        sql_query = f"""
        SELECT COUNT(*) AS candidate_count
        FROM {KnowledgeBaseDocuments.__tablename__} d
        WHERE d.knowledge_base_id = :kb_id
            {filter_columns_clause}
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
                metadata_value
            FROM
                {KnowledgeBaseDocuments.__tablename__}
            WHERE
                {where_sql}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """
        return sql_query, params

    @staticmethod
    def get_update_tokens_query() -> str:
        """
        Generate SQL query to update text search tokens.

        Returns:
            SQL query string
        """
        return "UPDATE knowledge_base_embeddings SET token = to_tsvector('english', chunk_text) WHERE token IS NULL"
