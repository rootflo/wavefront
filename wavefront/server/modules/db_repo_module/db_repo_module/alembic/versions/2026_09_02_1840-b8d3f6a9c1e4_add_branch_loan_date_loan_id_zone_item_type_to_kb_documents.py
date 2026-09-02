"""add branch, loan_date, loan_id, zone, item_type columns to knowledge_base_documents

Real, indexed columns mirroring the equivalent keys already carried inside
the unindexed `metadata_value` JSON blob, so branch/date-window filtering
(e.g. the repeat-pledge exact-match check) can use a real btree index
instead of `metadata_value ->> 'field'` text extraction. `zone`/`item_type`
are not filtered on by any query yet -- added ahead of future filtering
needs, so no index for them yet (add one when a real query need arises,
same as `branch`/`loan_date`).

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
    op.add_column(
        'knowledge_base_documents',
        sa.Column('zone', sa.String(length=255), nullable=True),
    )
    op.add_column(
        'knowledge_base_documents',
        sa.Column('item_type', sa.String(length=255), nullable=True),
    )

    op.create_index(
        'ix_kbd_kb_id_branch_loan_date',
        'knowledge_base_documents',
        ['knowledge_base_id', 'branch', 'loan_date'],
    )


def downgrade() -> None:
    op.drop_index('ix_kbd_kb_id_branch_loan_date', table_name='knowledge_base_documents')
    op.drop_column('knowledge_base_documents', 'item_type')
    op.drop_column('knowledge_base_documents', 'zone')
    op.drop_column('knowledge_base_documents', 'loan_date')
    op.drop_column('knowledge_base_documents', 'branch')
    op.drop_column('knowledge_base_documents', 'loan_id')
