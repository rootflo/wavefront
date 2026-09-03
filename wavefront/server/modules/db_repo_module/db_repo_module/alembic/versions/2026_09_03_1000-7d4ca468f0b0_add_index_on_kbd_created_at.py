"""add index on knowledge_base_documents.created_at

Composite (knowledge_base_id, created_at) index, same pattern as the
filter1..filter6 indexes -- supports both a plain per-KB listing ordered
by created_at (already the default ORDER BY in get_documents_list_query)
and a per-KB created_at window filter (the new created_at_start/
created_at_end params on the /retrieve endpoint) via a real btree index.

Revision ID: 7d4ca468f0b0
Revises: b8d3f6a9c1e4
Create Date: 2026-09-03 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7d4ca468f0b0'
down_revision: Union[str, None] = 'b8d3f6a9c1e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'ix_kbd_kb_id_created_at',
        'knowledge_base_documents',
        ['knowledge_base_id', 'created_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_kbd_kb_id_created_at', table_name='knowledge_base_documents')
