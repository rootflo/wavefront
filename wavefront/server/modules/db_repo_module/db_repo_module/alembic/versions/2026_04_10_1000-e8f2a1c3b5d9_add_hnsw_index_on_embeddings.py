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
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction block.
    # SQLAlchemy 2.x autobegins a transaction on op.get_bind(), and
    # execution_options(isolation_level=AUTOCOMMIT) is rejected while a
    # Transaction object is active. We get a fresh AUTOCOMMIT connection
    # directly from the underlying sync engine instead.
    bind = op.get_bind()
    sync_engine = getattr(bind.engine, 'sync_engine', bind.engine)

    with sync_engine.execution_options(isolation_level='AUTOCOMMIT').connect() as conn:
        conn.execute(text("SET maintenance_work_mem = '2GB'"))

        conn.execute(
            text("""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS
                ix_kbe_embedding_vector_hnsw_cosine
            ON knowledge_base_embeddings
            USING hnsw ((embedding_vector::vector(512)) vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
        """)
        )

        conn.execute(
            text("""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS
                ix_kbe_embedding_vector_1_hnsw_cosine
            ON knowledge_base_embeddings
            USING hnsw ((embedding_vector_1::vector(1024)) vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
        """)
        )

        conn.execute(
            text("""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS
                ix_kbe_token_gin
            ON knowledge_base_embeddings
            USING gin (token)
        """)
        )


def downgrade() -> None:
    bind = op.get_bind()
    sync_engine = getattr(bind.engine, 'sync_engine', bind.engine)

    with sync_engine.execution_options(isolation_level='AUTOCOMMIT').connect() as conn:
        conn.execute(
            text(
                'DROP INDEX CONCURRENTLY IF EXISTS ix_kbe_embedding_vector_hnsw_cosine'
            )
        )
        conn.execute(
            text(
                'DROP INDEX CONCURRENTLY IF EXISTS ix_kbe_embedding_vector_1_hnsw_cosine'
            )
        )
        conn.execute(text('DROP INDEX CONCURRENTLY IF EXISTS ix_kbe_token_gin'))
