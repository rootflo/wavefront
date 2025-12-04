"""add new columns in knowledge base tables

Revision ID: 6742f38ca303
Revises: d54e5612306e
Create Date: 2025-10-24 07:13:22.702999

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import pgvector

# revision identifiers, used by Alembic.
revision: str = '6742f38ca303'
down_revision: Union[str, None] = 'd54e5612306e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'knowledge_base_embeddings',
        sa.Column(
            'embedding_vector_1', pgvector.sqlalchemy.vector.VECTOR(), nullable=True
        ),
    )
    op.add_column(
        'knowledge_bases', sa.Column('vector_size_1', sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('knowledge_bases', 'vector_size_1')
    op.drop_column('knowledge_base_embeddings', 'embedding_vector_1')
