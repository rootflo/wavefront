"""RAG: index status, BGE-M3 text embeddings, strict KB types, drop KB inferences

Revision ID: e2a7c5d81f94
Revises: c3f8a91d42be
Create Date: 2026-10-03 16:00:00.000000

One migration for the RAG changes in this PR, applied in this order:

1. Document index status. knowledge_base_documents gets index_status
   (QUEUED / IN_PROGRESS / COMPLETE / FAILED), index_error and
   index_status_updated_at, so each document can be tracked through RAG
   indexing. Existing rows stay NULL: there is no record of whether they were
   indexed.

2. BGE-M3 text embeddings. knowledge_base_embeddings gets dedicated text
   columns, each with its own HNSW index, so text and image vectors never share
   a column or graph:
     text_embedding         vector(1024)       cosine
     text_sparse_embedding  sparsevec(250002)  inner product
   sparsevec needs pgvector >= 0.7 and retrieval's iterative HNSW scans need
   >= 0.8. A database created on the old ankane/pgvector image has 0.5.x, so
   this first runs ALTER EXTENSION vector UPDATE and stops with a clear error
   if the server's pgvector is still older than 0.8. Existing text embeddings
   came from a different model and stay in embedding_vector; text documents
   must be re-ingested to get BGE-M3 vectors.

3. Strict knowledge base types. knowledge_bases.type was a free-text label;
   it now decides the embedding models and accepted files, so it must be one of
     text   BGE-M3:        vector_size 1024, no vector_size_1
     image  CLIP + DINOv3: vector_size 512, vector_size_1 1024
   Existing rows are classified by what they were configured to store (a
   vector_size_1 means CLIP + DINO, so image; anything else is text), their
   vector sizes reset to the type's, and a CHECK constraint added. The
   free-text labels are overwritten.

4. Drop knowledge_base_inferences. KB "inferences" (a stored system prompt +
   LLM config per KB, used by /augment and the querying_knowlegebase agent
   tool) are removed; RAG over a knowledge base goes through the chatbot
   feature instead. The stored prompts are deleted with the table.

Downgrade reverses all four. It recreates an empty knowledge_base_inferences
table but does not restore its rows, the original KB type labels and sizes,
or anything in the dropped columns.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import SPARSEVEC, Vector


revision: str = 'e2a7c5d81f94'
down_revision: Union[str, None] = 'c3f8a91d42be'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TEXT_EMBEDDING_DIM = 1024
TEXT_SPARSE_EMBEDDING_DIM = 250002
# 0.7 added sparsevec; 0.8 added the iterative HNSW scans that retrieval
# turns on (hnsw.iterative_scan), and SET LOCAL errors on older versions.
MIN_PGVECTOR = (0, 8, 0)


def _pgvector_version(conn) -> tuple:
    version = conn.execute(
        sa.text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
    ).scalar()
    if version is None:
        return ()
    return tuple(int(part) for part in version.split('.')[:3])


def _require_pgvector(conn) -> None:
    if _pgvector_version(conn) >= MIN_PGVECTOR:
        return
    # Upgrade the installed extension to the newest version the server has.
    conn.execute(sa.text('ALTER EXTENSION vector UPDATE'))
    installed = _pgvector_version(conn)
    if installed < MIN_PGVECTOR:
        found = '.'.join(map(str, installed)) or 'not installed'
        raise RuntimeError(
            f'pgvector >= 0.8 is required (sparsevec, iterative HNSW scans), '
            f'found {found}. Use a Postgres image/server with a newer pgvector '
            '(e.g. pgvector/pgvector:pg15 instead of ankane/pgvector) and re-run.'
        )


def upgrade() -> None:
    # Fail before changing anything if pgvector can't support step 2.
    _require_pgvector(op.get_bind())

    # 1. Document index status
    op.add_column(
        'knowledge_base_documents',
        sa.Column('index_status', sa.String(), nullable=True),
    )
    op.add_column(
        'knowledge_base_documents',
        sa.Column('index_error', sa.Text(), nullable=True),
    )
    op.add_column(
        'knowledge_base_documents',
        sa.Column('index_status_updated_at', sa.DateTime(), nullable=True),
    )

    # 2. BGE-M3 text embedding columns and their HNSW indexes
    op.add_column(
        'knowledge_base_embeddings',
        sa.Column('text_embedding', Vector(TEXT_EMBEDDING_DIM), nullable=True),
    )
    op.add_column(
        'knowledge_base_embeddings',
        sa.Column(
            'text_sparse_embedding',
            SPARSEVEC(TEXT_SPARSE_EMBEDDING_DIM),
            nullable=True,
        ),
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_kbe_text_embedding_hnsw_cosine '
        'ON knowledge_base_embeddings USING hnsw (text_embedding vector_cosine_ops)'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_kbe_text_sparse_embedding_hnsw_ip '
        'ON knowledge_base_embeddings '
        'USING hnsw (text_sparse_embedding sparsevec_ip_ops)'
    )

    # 3. Strict knowledge base types (text / image), sizes derived from type
    op.execute(
        """
        UPDATE knowledge_bases
        SET type = CASE
                WHEN vector_size_1 IS NOT NULL AND vector_size_1 > 0 THEN 'image'
                ELSE 'text'
            END
        """
    )
    op.execute(
        """
        UPDATE knowledge_bases
        SET vector_size = CASE WHEN type = 'image' THEN 512 ELSE 1024 END,
            vector_size_1 = CASE WHEN type = 'image' THEN 1024 ELSE NULL END
        """
    )
    op.create_check_constraint(
        'ck_knowledge_bases_type', 'knowledge_bases', "type IN ('text', 'image')"
    )

    # 4. Drop knowledge base inferences
    op.drop_table('knowledge_base_inferences')


def downgrade() -> None:
    # 4. Recreate the (empty) inferences table as it was
    op.create_table(
        'knowledge_base_inferences',
        sa.Column('inference_id', sa.Uuid(), nullable=False),
        sa.Column('knowledge_base_id', sa.Uuid(), nullable=False),
        sa.Column('inference_content', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('config_id', sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ['knowledge_base_id'], ['knowledge_bases.id'], ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['config_id'],
            ['llm_inference_config.id'],
            name='fk_kb_inferences_config_id',
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('inference_id'),
    )
    op.create_index(
        op.f('ix_knowledge_base_inferences_inference_id'),
        'knowledge_base_inferences',
        ['inference_id'],
        unique=False,
    )

    # 3. Free-text knowledge base types again (labels are not restored)
    op.drop_constraint('ck_knowledge_bases_type', 'knowledge_bases', type_='check')

    # 2. Text embedding columns
    op.execute('DROP INDEX IF EXISTS ix_kbe_text_sparse_embedding_hnsw_ip')
    op.execute('DROP INDEX IF EXISTS ix_kbe_text_embedding_hnsw_cosine')
    op.drop_column('knowledge_base_embeddings', 'text_sparse_embedding')
    op.drop_column('knowledge_base_embeddings', 'text_embedding')

    # 1. Document index status
    op.drop_column('knowledge_base_documents', 'index_status_updated_at')
    op.drop_column('knowledge_base_documents', 'index_error')
    op.drop_column('knowledge_base_documents', 'index_status')
