import asyncio
from dataclasses import dataclass, field
import httpx
from typing import Any, Optional
import uuid
from fastapi import HTTPException, status
from knowledge_base_module.queries.generate_query import QueryGenerator
from db_repo_module.models.knowledge_base_embeddings import KnowledgeBaseEmbeddings
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from sqlalchemy.exc import SQLAlchemyError


@dataclass
class ImageMatch:
    """
    A single image search result, merged across the CLIP and DINO
    nearest-neighbor searches for one `document_id`.

    `clip_score`/`dino_score` default to 0 rather than `None` to
    distinguish "this model never returned this document" from a
    genuine near-zero similarity -- callers should check `matched_by`
    to tell the two apart.
    """

    document_id: uuid.UUID
    embedding_id: Any = None
    file_path: Optional[str] = None
    file_name: Optional[str] = None
    knowledge_base_id: Optional[uuid.UUID] = None
    metadata_value: Optional[dict] = None
    clip_score: float = 0.0
    dino_score: float = 0.0
    matched_by: list = field(default_factory=list)
    combined_score: float = 0.0
    similarity: float = 0.0


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
        filter1: Optional[str] = None,
        filter2: Optional[str] = None,
        filter3: Optional[str] = None,
        filter4: Optional[str] = None,
        filter5: Optional[str] = None,
        filter6: Optional[str] = None,
        document_date_start=None,
        document_date_end=None,
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
                filter1=filter1,
                filter2=filter2,
                filter3=filter3,
                filter4=filter4,
                filter5=filter5,
                filter6=filter6,
                document_date_start=document_date_start,
                document_date_end=document_date_end,
            )
        else:
            return []

    async def exact_match_dino(
        self,
        image_data: str,
        inference_url: str,
        kb_id: uuid.UUID,
        filter1: str,
        document_date_start,
        document_date_end,
        threshold: float,
        filter2: Optional[str] = None,
        filter3: Optional[str] = None,
        filter4: Optional[str] = None,
        filter5: Optional[str] = None,
        filter6: Optional[str] = None,
    ) -> list[dict]:
        """
        Exact (non-ANN) DINO similarity match, restricted to documents in
        `kb_id` whose real `filter1`/`document_date` columns fall within the
        given window. `filter1` and `document_date` are required; `filter2`
        through `filter6` are optional additional equality filters. All
        `filterN` columns are generic, caller-defined columns -- see
        `KnowledgeBaseDocuments` -- this service has no notion of what they
        mean semantically.

        Only the DINO embedding is fetched/compared -- this check is purely
        about near-duplicate/visual-similarity matching (the same use case
        `DINO_MATCH_SCORE_THRESHOLD` already serves in flo-api's spurious-image
        check), not general semantic (CLIP) similarity. The underlying query
        (`QueryGenerator.get_image_embedding_dino_exact_match`) never engages the
        HNSW index -- see that method's docstring -- so scores returned here
        are always exact, not approximate.
        """
        data = {'image_data': image_data}
        internal_api_url = f'{inference_url}/inference/v1/query/embeddings'
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(60.0, connect=30.0),
                limits=httpx.Limits(
                    max_keepalive_connections=20,
                    max_connections=100,
                    keepalive_expiry=60,
                ),
            ) as client:
                response = await client.post(internal_api_url, json=data)
                response.raise_for_status()
                embedding = response.json().get('data', {}).get('response', [])
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f'Inference service returned an error: {e}',
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f'Inference service is unreachable: {e}',
            )
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f'Inference service returned an unparseable response: {e}',
            )

        dino_embedding = next((e['dino'] for e in embedding if 'dino' in e), None)
        if not dino_embedding:
            return []

        try:
            sql_query, query_params = (
                self.query_generator.get_image_embedding_dino_exact_match(
                    dino_embedding,
                    kb_id,
                    filter1,
                    document_date_start,
                    document_date_end,
                    threshold,
                    filter2,
                    filter3,
                    filter4,
                    filter5,
                    filter6,
                )
            )
            return await self.knowledge_base_embeddings_repository.execute_query(
                sql_query,
                query_params,
            )
        except SQLAlchemyError as e:
            raise RuntimeError(
                f'Failed to execute the query for exact match retrieval: {e}'
            )

    async def image_retrieve_clip(
        self,
        clip_embedding,
        kb_id,
        top_k,
        query_filter,
        filter1: Optional[str] = None,
        filter2: Optional[str] = None,
        filter3: Optional[str] = None,
        filter4: Optional[str] = None,
        filter5: Optional[str] = None,
        filter6: Optional[str] = None,
        document_date_start=None,
        document_date_end=None,
    ):
        """Search for similar images using the CLIP embedding only."""
        params = {
            'kb_id': kb_id,
            'top_k': top_k,
            'filter1': filter1,
            'filter2': filter2,
            'filter3': filter3,
            'filter4': filter4,
            'filter5': filter5,
            'filter6': filter6,
            'document_date_start': document_date_start,
            'document_date_end': document_date_end,
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
        filter1: Optional[str] = None,
        filter2: Optional[str] = None,
        filter3: Optional[str] = None,
        filter4: Optional[str] = None,
        filter5: Optional[str] = None,
        filter6: Optional[str] = None,
        document_date_start=None,
        document_date_end=None,
    ):
        """
        Search for similar images using the DINO embedding only, as its own
        independent, KB-scoped nearest-neighbor search.
        """
        params = {
            'kb_id': kb_id,
            'top_k': top_k,
            'filter1': filter1,
            'filter2': filter2,
            'filter3': filter3,
            'filter4': filter4,
            'filter5': filter5,
            'filter6': filter6,
            'document_date_start': document_date_start,
            'document_date_end': document_date_end,
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
        filter1: Optional[str] = None,
        filter2: Optional[str] = None,
        filter3: Optional[str] = None,
        filter4: Optional[str] = None,
        filter5: Optional[str] = None,
        filter6: Optional[str] = None,
        document_date_start=None,
        document_date_end=None,
    ) -> list[ImageMatch]:
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

        Returns a list of `ImageMatch` objects rather than raw dicts, so
        the merge logic below has an explicit, typed shape to read and
        write instead of ad-hoc dict keys. Callers that need a
        JSON-serializable form (e.g. an HTTP response) should convert
        via `dataclasses.asdict()`.

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
            self.image_retrieve_clip(
                clip_embedding,
                kb_id,
                top_k,
                query_filter,
                filter1,
                filter2,
                filter3,
                filter4,
                filter5,
                filter6,
                document_date_start,
                document_date_end,
            ),
            self.image_retrieve_dino(
                dino_embedding,
                kb_id,
                top_k,
                query_filter,
                filter1,
                filter2,
                filter3,
                filter4,
                filter5,
                filter6,
                document_date_start,
                document_date_end,
            ),
        )

        merged: dict[uuid.UUID, ImageMatch] = {}

        def _base_match(doc_id, row) -> ImageMatch:
            return ImageMatch(
                document_id=doc_id,
                embedding_id=row.get('embedding_id'),
                file_path=row.get('file_path'),
                file_name=row.get('file_name'),
                knowledge_base_id=row.get('knowledge_base_id'),
                metadata_value=row.get('metadata_value'),
            )

        for row in clip_rows:
            doc_id = row['document_id']
            match = merged.setdefault(doc_id, _base_match(doc_id, row))
            match.clip_score = row.get('clip_score', 0) or 0
            if 'clip' not in match.matched_by:
                match.matched_by.append('clip')

        for row in dino_rows:
            doc_id = row['document_id']
            # Only created here if the document didn't already surface via
            # CLIP -- otherwise the existing match (with its clip_score and
            # shared fields already set) is reused and just gains a
            # dino_score.
            match = merged.setdefault(doc_id, _base_match(doc_id, row))
            match.dino_score = row.get('similarity', 0) or 0
            if 'dino' not in match.matched_by:
                match.matched_by.append('dino')

        results = list(merged.values())
        for match in results:
            match.combined_score = (
                match.clip_score * clip_weight + match.dino_score * dino_weight
            )
            match.similarity = match.combined_score

        results.sort(key=lambda m: m.combined_score, reverse=True)
        return results
