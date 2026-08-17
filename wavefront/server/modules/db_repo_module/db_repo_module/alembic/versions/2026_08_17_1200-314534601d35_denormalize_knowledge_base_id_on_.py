"""denormalize knowledge_base_id onto knowledge_base_embeddings

KB-scoped vector search (get_image_embedding_clip / get_image_embedding_dino)
filtered by knowledge_base_documents.knowledge_base_id via a join, which lives
on a different table than the HNSW-indexed embedding_vector column. Per
pgvector's filtering guidance, HNSW filtering is only pushed ahead of the ANN
walk when the filter column is on the same table as the vector column --
otherwise the filter is applied after the (ef_search-bounded) index scan, and
a small/selective knowledge base can silently get fewer than top_k results
even though matching rows exist. Denormalizing knowledge_base_id onto
knowledge_base_embeddings puts the filter on the same table as the vector.

Revision ID: 314534601d35
Revises: c7e2a1b4d9f3
Create Date: 2026-08-17 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '314534601d35'
down_revision: Union[str, None] = 'c7e2a1b4d9f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add as nullable first so existing rows can be backfilled before the
    # NOT NULL constraint is enforced.
    op.add_column(
        'knowledge_base_embeddings',
        sa.Column('knowledge_base_id', sa.Uuid(), nullable=True),
    )

    op.execute("""
        UPDATE knowledge_base_embeddings e
        SET knowledge_base_id = d.knowledge_base_id
        FROM knowledge_base_documents d
        WHERE e.document_id = d.id
    """)

    op.alter_column('knowledge_base_embeddings', 'knowledge_base_id', nullable=False)

    op.create_foreign_key(
        'fk_kbe_knowledge_base_id_knowledge_bases',
        'knowledge_base_embeddings',
        'knowledge_bases',
        ['knowledge_base_id'],
        ['id'],
        ondelete='CASCADE',
    )

    op.create_index(
        'ix_kbe_knowledge_base_id',
        'knowledge_base_embeddings',
        ['knowledge_base_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_kbe_knowledge_base_id', table_name='knowledge_base_embeddings')
    op.drop_constraint(
        'fk_kbe_knowledge_base_id_knowledge_bases',
        'knowledge_base_embeddings',
        type_='foreignkey',
    )
    op.drop_column('knowledge_base_embeddings', 'knowledge_base_id')
