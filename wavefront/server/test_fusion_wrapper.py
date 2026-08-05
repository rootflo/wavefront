"""
Standalone script to validate ImageRagRetrieve.image_retrieve_fused against
the local pgvector Docker setup (docker-compose.pgvector-test.yml), using the
planted rows from verify_fusion_embeddings.sql:

  - clip_only.png (33...31): perfect CLIP match, terrible DINO match
  - dino_only.png (33...32): terrible CLIP match, perfect DINO match
  - no_match.png  (33...33): terrible on both

Query vectors are the "positive" patterns used when seeding, so clip_only
should score ~1.0 on CLIP/~0 on DINO, dino_only the reverse, and no_match
should score ~0 on both and get excluded once real KB noise is present.

Run with: uv run python3 test_fusion_wrapper.py
"""

import asyncio
import sys
import types

sys.path.insert(0, 'modules/db_repo_module')
sys.path.insert(0, 'modules/knowledge_base_module')

# mssql_python only ships wheels for Linux/Windows, not this Mac. It's pulled
# in transitively by the datasource plugin but unused by this test, so stub
# it out to unblock the import chain.
_mssql_stub = types.ModuleType('mssql_python')
_mssql_stub.connect = lambda *a, **k: None
sys.modules.setdefault('mssql_python', _mssql_stub)

from db_repo_module.database.connection import DatabaseClient, DatabaseConfig
from db_repo_module.models.knowledge_base_embeddings import KnowledgeBaseEmbeddings
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from knowledge_base_module.services.image_rag_retrieve import ImageRagRetrieve

LOAN_KB_ID = '22222222-2222-2222-2222-222222222222'

CLIP_ONLY_DOC = '33333333-3333-3333-3333-333333333331'
DINO_ONLY_DOC = '33333333-3333-3333-3333-333333333332'
NO_MATCH_DOC = '33333333-3333-3333-3333-333333333333'


def pos_pattern(dim: int) -> list:
    """
    Matches verify_fusion_embeddings.sql's clip_pos/dino_pos, which uses
    1-indexed `generate_series(1, dim) i` with `CASE WHEN i % 2 = 0 THEN 1.0
    ELSE -1.0`. For 0-indexed Python position j, i = j + 1, so the "even i"
    branch lands on odd j.
    """
    return [1.0 if j % 2 == 1 else -1.0 for j in range(dim)]


async def main():
    db_config = DatabaseConfig(
        username='postgres',
        password='postgres',
        host='localhost',
        port='5433',
        db_name='floware',
    )
    db_client = DatabaseClient(db_config)
    repo = SQLAlchemyRepository(KnowledgeBaseEmbeddings, db_client)
    image_rag = ImageRagRetrieve(repo)

    # Query with the "positive" pattern so clip_only.png (embedding=clip_pos)
    # and dino_only.png (embedding_1=dino_pos) should be the perfect matches.
    clip_query = pos_pattern(512)
    dino_query = pos_pattern(1024)

    results = await image_rag.image_retrieve_fused(
        clip_embedding=clip_query,
        dino_embedding=dino_query,
        kb_id=LOAN_KB_ID,
        top_k=10,
        query_filter='',
        offset=0,
        limit=10,
    )

    print(f'Returned {len(results)} results\n')
    by_doc = {str(r['document_id']): r for r in results}

    for label, doc_id in [
        ('clip_only.png', CLIP_ONLY_DOC),
        ('dino_only.png', DINO_ONLY_DOC),
        ('no_match.png', NO_MATCH_DOC),
    ]:
        row = by_doc.get(doc_id)
        if row is None:
            print(f'{label:15s} MISSING from results')
            continue
        print(
            f"{label:15s} clip_score={row['clip_score']:.4f} "
            f"dino_score={row['dino_score']:.4f} "
            f"combined_score={row['combined_score']:.4f} "
            f"similarity={row['similarity']:.4f} "
            f"(similarity == combined_score: {row['similarity'] == row['combined_score']})"
        )

    print('\nRequired fields present on first result:',
          all(k in results[0] for k in
              ['embedding_id', 'chunk_text', 'chunk_index', 'document_id',
               'file_path', 'file_name', 'knowledge_base_id', 'metadata_value',
               'similarity']) if results else 'N/A (no results)')

    await db_client.close()


if __name__ == '__main__':
    asyncio.run(main())
