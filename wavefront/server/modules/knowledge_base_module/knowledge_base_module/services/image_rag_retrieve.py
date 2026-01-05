import httpx
from typing import Optional
import uuid
from knowledge_base_module.queries.generate_query import QueryGenerator
from db_repo_module.models.knowledge_base_embeddings import KnowledgeBaseEmbeddings
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from sqlalchemy.exc import SQLAlchemyError


class ImageRagRetrieve:
    def __init__(
        self,
        knowledge_base_embeddings_repository: SQLAlchemyRepository[
            KnowledgeBaseEmbeddings
        ],
    ):
        self.reranked_image = []
        self.query_generator = QueryGenerator()
        self.knowledge_base_embeddings_repository = knowledge_base_embeddings_repository

    async def retrieve_images(
        self,
        image_data: str,
        inference_url: str,
        kb_id: uuid.UUID,
        threshold: Optional[float] = None,
        top_k: Optional[int] = None,
        query_filter: Optional[str] = '',
        offset: Optional[int] = None,
        limit: Optional[int] = None,
    ):
        data = {'image_data': image_data}
        internal_api_url = f'{inference_url}/inference/v1/query/embeddings'
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=30.0),
            limits=httpx.Limits(
                max_keepalive_connections=20,
                max_connections=100,
                keepalive_expiry=60,
            ),
        ) as client:
            response = await client.post(internal_api_url, json=data)
            embedding = response.json().get('data', {}).get('response', [])

        if embedding:
            self.reranked_image = await self.image_retrieve(
                embedding[0]['clip'], kb_id, threshold, top_k, query_filter
            )
            reference_id_list = [
                str(data['document_id']) for data in self.reranked_image
            ]
            self.reranked_image = await self.image_retrieve_dino(
                embedding[1]['dino'],
                kb_id,
                reference_id_list,
                query_filter,
                offset,
                limit,
            )
            return self.reranked_image
        else:
            return []

    async def image_retrieve(self, embedding, kb_id, threshold, top_k, query_filter):
        """Search for similar images in the vector database"""

        # Use L2 distance for similarity search
        params = {
            'threshold': threshold or 0.5,
            'top_k': top_k or 50,
            'kb_id': kb_id,
        }
        try:
            # Get and execute the combined search query
            sql_query, query_params = self.query_generator.get_image_embedding(
                embedding, params, query_filter
            )
            retrieved_docs = (
                await self.knowledge_base_embeddings_repository.execute_query(
                    sql_query, query_params
                )
            )
            return retrieved_docs

        except SQLAlchemyError as e:
            # self.logger.error(f'Database error: {e}')
            raise RuntimeError(f'Failed to execute the query for retrieval images: {e}')

    async def image_retrieve_dino(
        self, embedding, kb_id, reference_id_list, query_filter, offset=None, limit=None
    ):
        """Search for similar images in the vector database"""

        # Use L2 distance for similarity search
        params = {
            'kb_id': kb_id,
            'reference_id_list': reference_id_list,
        }
        try:
            # Get and execute the combined search query
            sql_query, query_params = self.query_generator.get_image_embedding_dino(
                embedding, params, query_filter, offset, limit
            )
            retrieved_docs = (
                await self.knowledge_base_embeddings_repository.execute_query(
                    sql_query, query_params
                )
            )
            return retrieved_docs

        except SQLAlchemyError as e:
            raise RuntimeError(f'Failed to execute the query for retrieval images: {e}')
