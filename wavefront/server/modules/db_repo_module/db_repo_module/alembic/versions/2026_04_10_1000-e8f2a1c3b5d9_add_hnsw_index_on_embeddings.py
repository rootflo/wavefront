"""add hnsw index on knowledge_base_embeddings

Revision ID: e8f2a1c3b5d9
Revises: c7a9e2f4b1d0
Create Date: 2026-04-10 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'e8f2a1c3b5d9'
down_revision: Union[str, None] = 'c7a9e2f4b1d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # HNSW requires a dimensioned vector expression — the column is stored without
    # dimensions so we cast inline.
    # embedding_vector  → 512 dims (CLIP image / text embeddings)
    # embedding_vector_1 → 1024 dims (DINO image embeddings)
    #
    # CREATE INDEX CONCURRENTLY must run outside a transaction block.
    # We switch the connection to AUTOCOMMIT for the duration of this migration.
    connection = op.get_bind()
    connection.execution_options(isolation_level='AUTOCOMMIT')

    connection.execute(
        text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS
            ix_kbe_embedding_vector_hnsw_cosine
        ON knowledge_base_embeddings
        USING hnsw ((embedding_vector::vector(512)) vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)
    )

    connection.execute(
        text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS
            ix_kbe_embedding_vector_hnsw_l2
        ON knowledge_base_embeddings
        USING hnsw ((embedding_vector::vector(512)) vector_l2_ops)
        WITH (m = 16, ef_construction = 64)
    """)
    )

    connection.execute(
        text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS
            ix_kbe_embedding_vector_1_hnsw_cosine
        ON knowledge_base_embeddings
        USING hnsw ((embedding_vector_1::vector(1024)) vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)
    )

    connection.execute(
        text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS
            ix_kbe_token_gin
        ON knowledge_base_embeddings
        USING gin (token)
    """)
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execution_options(isolation_level='AUTOCOMMIT')

    connection.execute(
        text('DROP INDEX CONCURRENTLY IF EXISTS ix_kbe_embedding_vector_hnsw_cosine')
    )
    connection.execute(
        text('DROP INDEX CONCURRENTLY IF EXISTS ix_kbe_embedding_vector_hnsw_l2')
    )
    connection.execute(
        text('DROP INDEX CONCURRENTLY IF EXISTS ix_kbe_embedding_vector_1_hnsw_cosine')
    )
    connection.execute(text('DROP INDEX CONCURRENTLY IF EXISTS ix_kbe_token_gin'))
