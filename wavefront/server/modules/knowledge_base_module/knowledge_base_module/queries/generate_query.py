import re
from typing import Any, Dict, Tuple, List, Optional

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
            'ef_search': self.compute_ef_search(effective_limit),
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
        sql_query = f"""
            WITH vector_results AS (
                SELECT
                    e.id as embedding_id,
                    e.chunk_text,
                    e.chunk_index,
                    d.id as document_id,
                    d.file_path,
                    d.knowledge_base_id,
                    d.metadata_value,
                    1 - ((e.embedding_vector::vector(512)) <=> :query_embed ::vector(512)) as vector_score
                FROM
                    {KnowledgeBaseEmbeddings.__tablename__} e
                JOIN
                    {KnowledgeBaseDocuments.__tablename__} d ON e.document_id = d.id
                WHERE
                     d.knowledge_base_id = :kb_id {'AND (' + metadata_filter_clause_inner + ')' if metadata_filter_clause_inner else ''}
                ORDER BY
                    (e.embedding_vector::vector(512)) <=> :query_embed ::vector(512)
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
                    AND d.knowledge_base_id = :kb_id {'AND (' + metadata_filter_clause_inner + ')' if metadata_filter_clause_inner else ''}
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

        # Prepare query parameters
        params = {
            'query_embedding': query_embeddings,
            'kb_id': kb_id,
            'top_k': top_k,
            'ef_search': self.compute_ef_search(top_k),
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
            e.chunk_text,
            e.chunk_index,
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
            {'AND (' + metadata_filter_clause + ')' if metadata_filter_clause else ''}
        ORDER BY (e.embedding_vector::vector(512)) <=> :query_embedding ::vector(512)
        LIMIT :top_k
        """

        return sql_query, params

    def get_image_embedding_dino(
        self,
        query_embeddings: list,
        params: Dict[str, Any],
        filter: str,
        offset: Optional[int] = None,
        limit: Optional[int] = None,
    ):
        kb_id = str(params.get('kb_id'))
        # Use limit if provided, otherwise use top_k
        effective_limit = limit if limit is not None else int(params.get('top_k', 10))
        reference_id_list: List[Any] = params.get('reference_id_list', [])
        effective_offset = offset if offset is not None else 0

        if reference_id_list:
            processed_reference_ids = [
                str(id) for id in reference_id_list
            ]  # Use list instead of tuple
        else:
            processed_reference_ids = []

        params = {
            'query_embedding': query_embeddings,
            'kb_id': kb_id,
            'reference_ids': processed_reference_ids,
            'offset': effective_offset,
            'limit': effective_limit,
            'ef_search': self.compute_ef_search(effective_limit),
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

        # NOTE: filtering on d.id = ANY(:reference_ids) lives in the same
        # scope as the distance ORDER BY/LIMIT. reference_ids is normally a
        # small, already-known candidate set (e.g. a CLIP shortlist), so
        # this lets Postgres fetch exactly those rows and compute an exact
        # distance directly, instead of running an unfiltered global ANN
        # search first and hoping those specific rows survive it.
        sql_query = f"""
        SELECT
            e.id AS embedding_id,
            e.chunk_text,
            e.chunk_index,
            d.id AS document_id,
            d.file_path,
            d.file_name,
            d.knowledge_base_id,
            d.metadata_value,
            1 - ((e.embedding_vector_1::vector(1024)) <=> :query_embedding ::vector(1024)) AS similarity
        FROM {KnowledgeBaseEmbeddings.__tablename__} e
        JOIN {KnowledgeBaseDocuments.__tablename__} d ON e.document_id = d.id
        WHERE d.knowledge_base_id = :kb_id
            {('AND d.id = ANY(:reference_ids)' if processed_reference_ids else '')}
            {'AND (' + metadata_filter_clause + ')' if metadata_filter_clause else ''}
        ORDER BY similarity DESC
        LIMIT :limit OFFSET :offset
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
