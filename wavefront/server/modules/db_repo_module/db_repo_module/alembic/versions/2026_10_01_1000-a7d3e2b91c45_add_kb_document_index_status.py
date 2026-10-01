"""add index status to knowledge base documents

Revision ID: a7d3e2b91c45
Revises: c3f8a91d42be
Create Date: 2026-10-01 10:00:00.000000

Tracks each document through RAG indexing: QUEUED (set by floware when it is
put on the RAG queue), then IN_PROGRESS / COMPLETE / FAILED reported by the
rag_ingestion worker. Existing rows are left NULL: there is no record of
whether they were indexed.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7d3e2b91c45'
down_revision: Union[str, None] = 'c3f8a91d42be'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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


def downgrade() -> None:
    op.drop_column('knowledge_base_documents', 'index_status_updated_at')
    op.drop_column('knowledge_base_documents', 'index_error')
    op.drop_column('knowledge_base_documents', 'index_status')
