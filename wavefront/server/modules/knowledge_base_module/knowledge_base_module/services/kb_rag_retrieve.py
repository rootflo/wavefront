import logging
from typing import Optional
import uuid

from db_repo_module.models.knowledge_base_documents import KnowledgeBaseDocuments
from db_repo_module.models.knowledge_base_embeddings import KnowledgeBaseEmbeddings
from db_repo_module.models.llm_inference_config import LlmInferenceConfig
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from knowledge_base_module.embeddings.llm import LLMModelFunc
from knowledge_base_module.embeddings.embed import EmbeddingFunc
from knowledge_base_module.queries.generate_query import QueryGenerator
from sqlalchemy.exc import SQLAlchemyError


class KBRagResponse:
    """Configuration class for EmailRag settings."""

    def __init__(
        self,
        knowledge_base_documents_repository: SQLAlchemyRepository[
            KnowledgeBaseDocuments
        ],
        knowledge_base_embeddings_repository: SQLAlchemyRepository[
            KnowledgeBaseEmbeddings
        ],
        inference_url,
    ):
        self.embedding = EmbeddingFunc(inference_url)
        self.knowledge_base_documents_repository = knowledge_base_documents_repository
        self.knowledge_base_embeddings_repository = knowledge_base_embeddings_repository
        self.logger = logging.getLogger(__name__)
        self.query_generator = QueryGenerator()
        self.llm_model_func = LLMModelFunc()
        self.reranked_docs = []

    async def retrieve_documents(
        self,
        query: str,
        kb_id: uuid.UUID,
        threshold: Optional[float] = None,
        vector_weight: Optional[float] = None,
        keyword_weight: Optional[float] = None,
        query_filter: Optional[str] = '',
        offset: Optional[int] = None,
        limit: Optional[int] = None,
        filter1: Optional[str] = None,
        filter2: Optional[str] = None,
        filter3: Optional[str] = None,
        filter4: Optional[str] = None,
        filter5: Optional[str] = None,
        filter6: Optional[str] = None,
        document_date_start=None,
        document_date_end=None,
        created_at_start=None,
        created_at_end=None,
    ) -> list:
        """
        Retrieve documents for a specific knowledge base

        Args:
            query: Text query for search
            kb_id: Knowledge base ID to filter results
            threshold: Cosine similarity threshold (default: 0.2)
            top_k: Number of results to return (default: 10)
            vector_weight: Weight for vector similarity score (default: 0.7)
            keyword_weight: Weight for keyword similarity score (default: 0.3)
            filter1..filter6: Optional equality filters on
                knowledge_base_documents.filterN
            document_date_start/document_date_end: Optional document_date
                window (both required together)
            created_at_start/created_at_end: Optional created_at window
                (both required together)

        Returns:
            List of retrieved documents
        """
        if not isinstance(query, str):
            raise ValueError('Query must be in string format')

        query_embedding = await self.embedding.embed_query(query)
        # Explicit None checks, so threshold=0 or a weight of 0 is honoured
        # rather than replaced by the default.
        params = {
            'threshold': 0.2 if threshold is None else threshold,
            'vector_weight': 0.7 if vector_weight is None else vector_weight,
            'keyword_weight': 0.3 if keyword_weight is None else keyword_weight,
            'kb_id': kb_id,
        }

        reranked_docs = await self.combined_search_with_reranking(
            query_embedding['dense'],
            query_embedding['sparse'],
            params,
            query_filter,
            offset,
            limit,
            filter1,
            filter2,
            filter3,
            filter4,
            filter5,
            filter6,
            document_date_start,
            document_date_end,
            created_at_start,
            created_at_end,
        )
        for doc in reranked_docs:
            for key, value in doc.items():
                if isinstance(value, uuid.UUID):
                    doc[key] = str(value)
        return reranked_docs

    async def combined_search_with_reranking(
        self,
        query_dense: list,
        query_sparse: dict,
        params: dict,
        filter: str,
        offset: Optional[int] = None,
        limit: Optional[int] = None,
        filter1: Optional[str] = None,
        filter2: Optional[str] = None,
        filter3: Optional[str] = None,
        filter4: Optional[str] = None,
        filter5: Optional[str] = None,
        filter6: Optional[str] = None,
        document_date_start=None,
        document_date_end=None,
        created_at_start=None,
        created_at_end=None,
    ) -> list:
        """
        Hybrid BGE-M3 dense + sparse search in a single SQL query, filtered by
        knowledge base ID (see QueryGenerator.get_combined_search_query).

        Args:
            query_dense: The query's BGE-M3 dense vector
            query_sparse: The query's BGE-M3 sparse vector, {indices, values}
            params: Dictionary containing query parameters

        Returns:
            List of retrieved documents
        """
        try:
            # token is now set at insert time in store_embeddings, so rows never
            # arrive NULL and this search never needs to backfill it. Removed the
            # per-request UPDATE ... WHERE token IS NULL that used to run here on
            # every single call -- an unindexed full-table scan on every search,
            # regardless of whether anything matched.

            # Get and execute the combined search query
            sql_query, query_params = self.query_generator.get_combined_search_query(
                query_dense,
                query_sparse,
                params,
                filter,
                offset,
                limit,
                filter1,
                filter2,
                filter3,
                filter4,
                filter5,
                filter6,
                document_date_start,
                document_date_end,
                created_at_start,
                created_at_end,
            )
            # Sets hnsw.ef_search and iterative scans for this query, so the
            # KB/filter conditions (applied after the HNSW scan) don't leave
            # the candidate searches short -- pgvector otherwise stops at 40
            # candidates across the whole table.
            ef_search = self.query_generator.compute_ef_search(
                query_params['candidate_limit']
            )
            retrieved_docs = (
                await self.knowledge_base_embeddings_repository.execute_query(
                    sql_query,
                    query_params,
                    ef_search=ef_search,
                )
            )
            return retrieved_docs

        except SQLAlchemyError as e:
            self.logger.error(f'Database error: {e}')
            raise RuntimeError(
                f'Failed to execute the query for retrieval documents: {e}'
            )

    async def query(
        self,
        query: str,
        kb_id: uuid.UUID,
        prompt: str,
        threshold: Optional[float] = None,
        vector_weight: Optional[float] = None,
        keyword_weight: Optional[float] = None,
        model: Optional[str] = 'gemini-2.5-pro',
        query_filter: Optional[str] = '',
        offset: Optional[int] = None,
        limit: Optional[int] = None,
        llm_config: Optional[LlmInferenceConfig] = None,
    ):
        """
        Rag Response for a specific knowledge base

        Args:
            query: Text query for search
            kb_id: Knowledge base ID to filter results
            threshold: Cosine similarity threshold (default: 0.2)
            top_k: Number of results to return (default: 10)
            vector_weight: Weight for vector similarity score (default: 0.7)
            keyword_weight: Weight for keyword similarity score (default: 0.3)
            model: Model name (used if llm_config not provided)
            query_filter: Optional filter query
            offset: Optional offset for pagination
            limit: Optional limit for pagination
            llm_config: Optional LLM inference configuration

        Returns:
            Rag Response in json or string format
        """
        retrieved_docs = await self.retrieve_documents(
            query,
            kb_id,
            threshold,
            vector_weight,
            keyword_weight,
            query_filter,
            offset,
            limit,
        )
        content = '\n--New Chunk--\n'.join(
            [data['chunk_text'] for data in retrieved_docs]
        )
        sys_prompt = prompt.format(
            content_data=content,
        )

        response = await self.llm_model_func.generate_response(
            query, sys_prompt, model, llm_config
        )
        return response
