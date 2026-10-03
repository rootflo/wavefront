"""add BGE-M3 text embedding columns to knowledge_base_embeddings

Revision ID: b4e9c7d21a63
Revises: a7d3e2b91c45
Create Date: 2026-10-02 12:00:00.000000

Text knowledge bases now embed with BGE-M3 only: dense vectors are 1024-dim,
which the existing embedding_vector::vector(512) expression index rejects, and
sparse (lexical) vectors need pgvector's sparsevec type.

Adds dedicated columns, each with its own HNSW index, so text and image
vectors never share a column or graph:
  text_embedding         vector(1024)       cosine
  text_sparse_embedding  sparsevec(250002)  inner product

sparsevec needs pgvector >= 0.7, and retrieval's iterative HNSW scans need
>= 0.8. A database created on the old ankane/pgvector
image has 0.5.x installed, so this first runs ALTER EXTENSION vector UPDATE,
and stops with a clear error if the server's pgvector is still older than 0.8.

Existing text embeddings came from a different model and stay in
embedding_vector; text documents must be re-ingested to get BGE-M3 vectors.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import SPARSEVEC, Vector


revision: str = 'b4e9c7d21a63'
down_revision: Union[str, None] = 'a7d3e2b91c45'
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


def _require_sparsevec_support(conn) -> None:
    if _pgvector_version(conn) >= MIN_PGVECTOR:
        return
    # Upgrade the installed extension to the newest version the server has.
    conn.execute(sa.text('ALTER EXTENSION vector UPDATE'))
    installed = _pgvector_version(conn)
    if installed < MIN_PGVECTOR:
        found = '.'.join(map(str, installed)) or 'not installed'
        raise RuntimeError(
            f'pgvector >= 0.8 is required (sparsevec, iterative HNSW scans), '
            f'found {found}. Use a '
            'Postgres image/server with a newer pgvector (e.g. '
            'pgvector/pgvector:pg15 instead of ankane/pgvector) and re-run.'
        )


def upgrade() -> None:
    _require_sparsevec_support(op.get_bind())

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


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS ix_kbe_text_sparse_embedding_hnsw_ip')
    op.execute('DROP INDEX IF EXISTS ix_kbe_text_embedding_hnsw_cosine')
    op.drop_column('knowledge_base_embeddings', 'text_sparse_embedding')
    op.drop_column('knowledge_base_embeddings', 'text_embedding')
