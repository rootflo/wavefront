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
                    1 - (e.embedding_vector <=> :query_embed ::vector) as vector_score
                FROM
                    {KnowledgeBaseEmbeddings.__tablename__} e
                JOIN
                    {KnowledgeBaseDocuments.__tablename__} d ON e.document_id = d.id
                WHERE
                     d.knowledge_base_id = :kb_id {'AND (' + metadata_filter_clause_inner + ')' if metadata_filter_clause_inner else ''}
                ORDER BY
                    vector_score DESC
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

    def get_image_embedding(
        self, query_embeddings: list, params: Dict[str, Any], filter: str
    ):
        kb_id = str(params.get('kb_id'))
        top_k = int(params.get('top_k', 10))

        # Prepare query parameters
        params = {
            'query_embedding': query_embeddings,
            'kb_id': kb_id,
            'top_k': top_k,
        }
        metadata_filter_clause_final = ''
        if filter:
            where_clause, filter_params = self.odata_parser.prepare_odata_filter(filter)
            if where_clause and filter_params:
                metadata_filter_clause_final = self.build_metadata_clause(
                    where_clause,
                    filter_params,
                    lambda field: f"(d.metadata_value ->> '{field}')",
                )
                params.update(filter_params)
        sql_query = f"""
        WITH ranked_embeddings AS (
            SELECT
                e.id AS embedding_id,
                e.chunk_text,
                e.chunk_index,
                d.id AS document_id,
                d.file_path,
                d.file_name,
                d.knowledge_base_id,
                d.metadata_value,
                e.embedding_vector <-> :query_embedding ::vector AS distance
            FROM
                {KnowledgeBaseEmbeddings.__tablename__} e
            JOIN
                {KnowledgeBaseDocuments.__tablename__} d ON e.document_id = d.id
            WHERE
                d.knowledge_base_id = :kb_id {'AND (' + metadata_filter_clause_final + ')' if metadata_filter_clause_final else ''}
            ORDER BY distance ASC
        )
        SELECT
            *
        FROM
            ranked_embeddings
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
            'top_k': effective_limit,
            'reference_ids': processed_reference_ids,
            'offset': effective_offset,
            'limit': effective_limit,
        }

        metadata_filter_clause_final = ''
        if filter:
            where_clause, filter_params = self.odata_parser.prepare_odata_filter(filter)
            if where_clause and filter_params:
                metadata_filter_clause_final = self.build_metadata_clause(
                    where_clause,
                    filter_params,
                    lambda field: f"(d.metadata_value ->> '{field}')",
                )
                params.update(filter_params)
        # Use ANY operator for PostgreSQL array matching
        reference_filter = (
            'AND e.document_id = ANY(:reference_ids)' if processed_reference_ids else ''
        )

        sql_query = f"""
        WITH ranked_embeddings AS (
            SELECT
                e.id AS embedding_id,
                e.chunk_text,
                e.chunk_index,
                d.id AS document_id,
                d.file_path,
                d.file_name,
                d.knowledge_base_id,
                d.metadata_value,
                (1 - (e.embedding_vector_1 <=> :query_embedding ::vector)) AS similarity
            FROM {KnowledgeBaseEmbeddings.__tablename__} e
            JOIN {KnowledgeBaseDocuments.__tablename__} d ON e.document_id = d.id
            WHERE
                d.knowledge_base_id = :kb_id {reference_filter} {'AND (' + metadata_filter_clause_final + ')' if metadata_filter_clause_final else ''}
            ORDER BY similarity DESC
        )
        SELECT
            *
        FROM
            ranked_embeddings
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
        return "UPDATE knowledge_base_embeddings SET token = to_tsvector('english', chunk_text)"
