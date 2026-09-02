"""add generic filter1..filter6 and document_date columns to knowledge_base_documents

Real, indexed columns mirroring keys already carried inside the unindexed
`metadata_value` JSON blob, so date-window/attribute filtering (e.g. the
repeat-pledge exact-match check) can use a real btree index instead of
`metadata_value ->> 'field'` text extraction.

Deliberately generic (`filter1`..`filter6` + `document_date`) rather than
domain-named (e.g. `branch`/`loan_id`) -- wavefront is a shared KB/RAG
service used by multiple callers, so it shouldn't encode any one caller's
business vocabulary. Each caller owns the mapping of its own fields onto
these generic slots (e.g. flo-api currently maps branch->filter1,
zone->filter2, item_type->filter3, loan_id->filter4); filter5/filter6 are
headroom for future filter needs, not filtered on by any query yet. Only
`filter1` is indexed today (paired with `document_date`) -- add more
indexes when a real query need arises for the other slots.

Revision ID: b8d3f6a9c1e4
Revises: c7e2a1b4d9f3
Create Date: 2026-09-02 18:40:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b8d3f6a9c1e4'
down_revision: Union[str, None] = 'c7e2a1b4d9f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'knowledge_base_documents',
        sa.Column('document_date', sa.DateTime(), nullable=True),
    )
    op.add_column(
        'knowledge_base_documents',
        sa.Column('filter1', sa.String(length=255), nullable=True),
    )
    op.add_column(
        'knowledge_base_documents',
        sa.Column('filter2', sa.String(length=255), nullable=True),
    )
    op.add_column(
        'knowledge_base_documents',
        sa.Column('filter3', sa.String(length=255), nullable=True),
    )
    op.add_column(
        'knowledge_base_documents',
        sa.Column('filter4', sa.String(length=255), nullable=True),
    )
    op.add_column(
        'knowledge_base_documents',
        sa.Column('filter5', sa.String(length=255), nullable=True),
    )
    op.add_column(
        'knowledge_base_documents',
        sa.Column('filter6', sa.String(length=255), nullable=True),
    )

    op.create_index(
        'ix_kbd_kb_id_filter1_document_date',
        'knowledge_base_documents',
        ['knowledge_base_id', 'filter1', 'document_date'],
    )


def downgrade() -> None:
    op.drop_index(
        'ix_kbd_kb_id_filter1_document_date', table_name='knowledge_base_documents'
    )
    op.drop_column('knowledge_base_documents', 'filter6')
    op.drop_column('knowledge_base_documents', 'filter5')
    op.drop_column('knowledge_base_documents', 'filter4')
    op.drop_column('knowledge_base_documents', 'filter3')
    op.drop_column('knowledge_base_documents', 'filter2')
    op.drop_column('knowledge_base_documents', 'filter1')
    op.drop_column('knowledge_base_documents', 'document_date')
