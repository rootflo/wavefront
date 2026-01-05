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
from sqlalchemy import text
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
        embedding_url,
    ):
        self.embedding = EmbeddingFunc(embedding_url)
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

        Returns:
            List of retrieved documents
        """
        if not isinstance(query, str):
            raise ValueError('Query must be in string format')

        query_embeddings = self.embedding.generate_chunk_embeddings([query])
        params = {
            'threshold': threshold or 0.2,
            'vector_weight': vector_weight or 0.7,
            'keyword_weight': keyword_weight or 0.3,
            'kb_id': kb_id,
        }

        reranked_docs = await self.combined_search_with_reranking(
            query, query_embeddings, params, query_filter, offset, limit
        )
        for doc in reranked_docs:
            for key, value in doc.items():
                if isinstance(value, uuid.UUID):
                    doc[key] = str(value)
        return reranked_docs

    async def combined_search_with_reranking(
        self,
        query: str,
        query_embeddings: str,
        params: dict,
        filter: str,
        offset: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> list:
        """
        Perform combined vector and keyword search with reranking in a single SQL query,
        filtered by knowledge base ID.

        Args:
            query: The search query text
            query_embeddings: The vector embeddings of the query
            params: Dictionary containing query parameters

        Returns:
            List of retrieved documents
        """
        try:
            async with self.knowledge_base_embeddings_repository.session() as session:
                # Update text search tokens
                update_stmt = text(self.query_generator.get_update_tokens_query())
                await session.execute(update_stmt)
                await session.commit()

                # Get and execute the combined search query
                sql_query, query_params = (
                    self.query_generator.get_combined_search_query(
                        query, query_embeddings, params, filter, offset, limit
                    )
                )
                retrieved_docs = (
                    await self.knowledge_base_embeddings_repository.execute_query(
                        sql_query, query_params
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
