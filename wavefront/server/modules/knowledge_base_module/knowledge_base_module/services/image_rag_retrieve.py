import asyncio
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
        self.query_generator = QueryGenerator()
        self.knowledge_base_embeddings_repository = knowledge_base_embeddings_repository

    async def retrieve_images(
        self,
        image_data: str,
        inference_url: str,
        kb_id: uuid.UUID,
        top_k: Optional[int] = None,
        query_filter: Optional[str] = '',
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

        clip_embedding = next((e['clip'] for e in embedding if 'clip' in e), None)
        dino_embedding = next((e['dino'] for e in embedding if 'dino' in e), None)

        if clip_embedding and dino_embedding:
            return await self.image_retrieve_clip_dino_union(
                clip_embedding,
                dino_embedding,
                kb_id,
                top_k,
                query_filter,
            )
        else:
            return []

    async def image_retrieve_clip(
        self,
        clip_embedding,
        kb_id,
        top_k,
        query_filter,
    ):
        """Search for similar images using the CLIP embedding only."""
        params = {
            'kb_id': kb_id,
            'top_k': top_k,
        }
        try:
            sql_query, query_params = self.query_generator.get_image_embedding_clip(
                clip_embedding, params, query_filter
            )
            ef_search = self.query_generator.compute_ef_search(top_k)
            return await self.knowledge_base_embeddings_repository.execute_query(
                sql_query,
                query_params,
                ef_search=ef_search,
            )
        except SQLAlchemyError as e:
            raise RuntimeError(f'Failed to execute the query for retrieval images: {e}')

    async def image_retrieve_dino(
        self,
        dino_embedding,
        kb_id,
        top_k,
        query_filter,
    ):
        """
        Search for similar images using the DINO embedding only, as its own
        independent, KB-scoped nearest-neighbor search.
        """
        params = {
            'kb_id': kb_id,
            'top_k': top_k,
        }
        try:
            sql_query, query_params = self.query_generator.get_image_embedding_dino(
                dino_embedding, params, query_filter
            )
            ef_search = self.query_generator.compute_ef_search(top_k)
            return await self.knowledge_base_embeddings_repository.execute_query(
                sql_query,
                query_params,
                ef_search=ef_search,
            )
        except SQLAlchemyError as e:
            raise RuntimeError(f'Failed to execute the query for retrieval images: {e}')

    async def image_retrieve_clip_dino_union(
        self,
        clip_embedding,
        dino_embedding,
        kb_id,
        top_k,
        query_filter,
        clip_weight: float = 0.5,
        dino_weight: float = 0.5,
    ):
        """
        Search for similar images by taking the union of independent CLIP
        and DINO nearest-neighbor searches (each KB-scoped and
        index-friendly), so a document surfaces if it ranks well under
        either embedding model rather than being required to independently
        survive both stages.

        The two searches run concurrently and are merged here in Python
        (instead of a single fused SQL query), which keeps each query's
        output shape identical to its standalone form and lets us control
        the final response shape explicitly -- including restoring a
        `similarity` field for callers that expect one.

        Each result also carries a `matched_by` list (e.g. `['clip']`,
        `['dino']`, or `['clip', 'dino']`) so callers can tell whether a
        `clip_score`/`dino_score` of `0` means "this model scored it near
        zero" or "this model never returned this document at all" --
        distinguishing genuine low scores from defaults.

        CLIP and DINO are each asked for their own real `top_k` (no
        overfetching) and the union is returned as-is, so the response
        naturally holds between `top_k` and `2 * top_k` results depending
        on how much the two models agree -- this avoids ever having to
        compare CLIP's and DINO's scores against each other just to decide
        which candidates get truncated away.
        """
        top_k = 10 if top_k is None else int(top_k)

        clip_rows, dino_rows = await asyncio.gather(
            self.image_retrieve_clip(clip_embedding, kb_id, top_k, query_filter),
            self.image_retrieve_dino(dino_embedding, kb_id, top_k, query_filter),
        )

        merged: dict = {}

        for row in clip_rows:
            doc_id = row['document_id']
            entry = merged.setdefault(
                doc_id, {**row, 'clip_score': 0, 'dino_score': 0, 'matched_by': []}
            )
            entry.update(row)
            entry['clip_score'] = row.get('clip_score', 0) or 0
            if 'clip' not in entry['matched_by']:
                entry['matched_by'].append('clip')

        for row in dino_rows:
            doc_id = row['document_id']
            entry = merged.setdefault(
                doc_id, {**row, 'clip_score': 0, 'dino_score': 0, 'matched_by': []}
            )
            # Only fill in fields the clip row didn't already provide
            # (e.g. embedding_id/chunk_text/file_path when a document only
            # surfaced via DINO), and never let DINO's own "similarity"
            # column leak through -- it's remapped to dino_score below and
            # "similarity" is recomputed as the final combined_score.
            for key, value in row.items():
                if key != 'similarity':
                    entry.setdefault(key, value)
            entry['dino_score'] = row.get('similarity', 0) or 0
            if 'dino' not in entry['matched_by']:
                entry['matched_by'].append('dino')

        results = []
        for entry in merged.values():
            combined_score = (
                entry.get('clip_score', 0) * clip_weight
                + entry.get('dino_score', 0) * dino_weight
            )
            entry['combined_score'] = combined_score
            entry['similarity'] = combined_score
            results.append(entry)

        results.sort(key=lambda r: r['combined_score'], reverse=True)
        return results
