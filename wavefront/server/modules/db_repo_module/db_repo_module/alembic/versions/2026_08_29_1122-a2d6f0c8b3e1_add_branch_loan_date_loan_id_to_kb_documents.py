"""add branch, loan_date, loan_id columns to knowledge_base_documents

Revision ID: a2d6f0c8b3e1
Revises: c7e2a1b4d9f3
Create Date: 2026-08-29 11:22:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a2d6f0c8b3e1'
down_revision: Union[str, None] = 'c7e2a1b4d9f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Real, indexed columns mirroring the equivalent keys already carried
    # inside the unindexed `metadata_value` JSON blob, so branch/date-window
    # filtering (e.g. the repeat-pledge exact-match check) can use a real
    # btree index instead of `metadata_value ->> 'field'` text extraction.
    op.add_column(
        'knowledge_base_documents',
        sa.Column('loan_id', sa.String(length=255), nullable=True),
    )
    op.add_column(
        'knowledge_base_documents',
        sa.Column('branch', sa.String(length=255), nullable=True),
    )
    op.add_column(
        'knowledge_base_documents',
        sa.Column('loan_date', sa.DateTime(), nullable=True),
    )

    op.create_index(
        'ix_kbd_kb_id_branch_loan_date',
        'knowledge_base_documents',
        ['knowledge_base_id', 'branch', 'loan_date'],
    )


def downgrade() -> None:
    op.drop_index('ix_kbd_kb_id_branch_loan_date', table_name='knowledge_base_documents')
    op.drop_column('knowledge_base_documents', 'loan_date')
    op.drop_column('knowledge_base_documents', 'branch')
    op.drop_column('knowledge_base_documents', 'loan_id')
