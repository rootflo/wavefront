import asyncio
from dataclasses import dataclass
import flo_lib.http as httpx
from typing import Any, Optional
import uuid
from fastapi import HTTPException, status
from knowledge_base_module.queries.generate_query import QueryGenerator
from db_repo_module.models.knowledge_base_embeddings import KnowledgeBaseEmbeddings
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from sqlalchemy.exc import SQLAlchemyError

# Hard ceiling on exact_match_dino's candidate count -- no config/env var can
# exceed this, so a misconfiguration can't fully disable the safety guard.
EXACT_MATCH_HARD_CEILING = 5_000

# Fallback candidate cap used when the caller doesn't supply one Deliberately conservative;
# tune based on real p95 latency measurements against the target KB size.
DEFAULT_EXACT_MATCH_MAX_CANDIDATES = 1_000

# Scores leave the API rounded to this many decimal places. Full-precision
# similarities give an attacker a fine-grained signal to follow when
# iteratively perturbing a query image (e.g. PGD-style adversarial search);
# coarse scores blunt that. Ranking and thresholding still use full
# precision -- rounding happens only once results are final.
SCORE_DECIMALS = 2


def _round_score(score: Any) -> float:
    return round(float(score or 0), SCORE_DECIMALS)


@dataclass
class ImageMatch:
    """
    A single image search result, merged across the CLIP and DINO
    nearest-neighbor searches for one `document_id`.

    This is the API response shape, so it names scores by role rather than
    by embedding model -- `primary_score` is the DINO similarity and
    `secondary_score` the CLIP similarity -- and does not say which model
    surfaced the document, so the models in use are not exposed.

    A score is 0 when that model did not return the document.
    """

    document_id: uuid.UUID
    embedding_id: Any = None
    file_path: Optional[str] = None
    file_name: Optional[str] = None
    knowledge_base_id: Optional[uuid.UUID] = None
    metadata_value: Optional[dict] = None
    primary_score: float = 0.0
    secondary_score: float = 0.0
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
        created_at_start=None,
        created_at_end=None,
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
                created_at_start=created_at_start,
                created_at_end=created_at_end,
            )
        else:
            return []

    async def exact_match_dino(
        self,
        image_data: str,
        inference_url: str,
        kb_id: uuid.UUID,
        filter1: Optional[str],
        document_date_start,
        document_date_end,
        threshold: float,
        filter2: Optional[str] = None,
        filter3: Optional[str] = None,
        filter4: Optional[str] = None,
        filter5: Optional[str] = None,
        filter6: Optional[str] = None,
        created_at_start=None,
        created_at_end=None,
        max_candidates: Optional[int] = None,
    ) -> list[dict]:
        """
        Exact (non-ANN) DINO similarity match over documents in `kb_id`,
        optionally narrowed by `filter1`..`filter6` and a required
        `document_date` (or `created_at`) window. All `filterN` columns are
        generic, caller-defined columns -- see `KnowledgeBaseDocuments` --
        this service has no notion of what they mean semantically.

        Only the DINO embedding is fetched/compared -- this check is purely
        about near-duplicate/visual-similarity matching (the same use case
        `DINO_MATCH_SCORE_THRESHOLD` already serves in flo-api's spurious-image
        check), not general semantic (CLIP) similarity. The underlying query
        (`QueryGenerator.get_image_embedding_dino_exact_match`) never engages the
        HNSW index -- see that method's docstring -- so scores returned here
        are always exact, not approximate.

        The candidate set is capped directly in SQL via `ORDER BY d.id LIMIT
        max_candidates + 1` (clamped to `EXACT_MATCH_HARD_CEILING`),
        so an oversized candidate set never gets fully brute-forced.
        The extra "+1" row lets us detect an overflow  (raise a 422)
        using just the row count of the one query already run.
        The `threshold` filter is applied in Python (after the overflow check)
        rather than in SQL, against the full-precision score; the returned
        `primary_score` is then rounded to `SCORE_DECIMALS` places.
        """
        effective_cap = min(
            max_candidates or DEFAULT_EXACT_MATCH_MAX_CANDIDATES,
            EXACT_MATCH_HARD_CEILING,
        )

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
                    str(kb_id),
                    filter1,
                    document_date_start,
                    document_date_end,
                    effective_cap,
                    filter2,
                    filter3,
                    filter4,
                    filter5,
                    filter6,
                    created_at_start,
                    created_at_end,
                )
            )
            raw_rows = await self.knowledge_base_embeddings_repository.execute_query(
                sql_query,
                query_params,
            )
        except SQLAlchemyError as e:
            raise RuntimeError(
                f'Failed to execute the query for exact match retrieval: {e}'
            )

        if len(raw_rows) > effective_cap:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    f'More than {effective_cap} documents match the given filters, '
                    'which exceeds the exact-match safety limit. Narrow your date '
                    'range or filters and try again.'
                ),
            )

        return [
            {**row, 'primary_score': _round_score(row['primary_score'])}
            for row in raw_rows
            if row['primary_score'] > threshold
        ]

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
        created_at_start=None,
        created_at_end=None,
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
            'created_at_start': created_at_start,
            'created_at_end': created_at_end,
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
        created_at_start=None,
        created_at_end=None,
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
            'created_at_start': created_at_start,
            'created_at_end': created_at_end,
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
        created_at_start=None,
        created_at_end=None,
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
                created_at_start,
                created_at_end,
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
                created_at_start,
                created_at_end,
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
            match.secondary_score = row.get('clip_score', 0) or 0

        for row in dino_rows:
            doc_id = row['document_id']
            # Only created here if the document didn't already surface via
            # CLIP -- otherwise the existing match (with its secondary_score
            # and shared fields already set) is reused and just gains a
            # primary_score.
            match = merged.setdefault(doc_id, _base_match(doc_id, row))
            match.primary_score = row.get('similarity', 0) or 0

        results = list(merged.values())
        for match in results:
            match.combined_score = (
                match.secondary_score * clip_weight + match.primary_score * dino_weight
            )
            match.similarity = match.combined_score

        results.sort(key=lambda m: m.combined_score, reverse=True)

        # Round only after sorting so ranking uses full-precision scores.
        for match in results:
            match.primary_score = _round_score(match.primary_score)
            match.secondary_score = _round_score(match.secondary_score)
            match.combined_score = _round_score(match.combined_score)
            match.similarity = _round_score(match.similarity)
        return results
