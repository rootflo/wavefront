"""Update the metadata column in knowledge base documents table

Revision ID: 9bd8b7884ab0
Revises: 6742f38ca303
Create Date: 2025-11-03 14:37:38.268823

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '9bd8b7884ab0'
down_revision: Union[str, None] = '22ec0134dcf8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'knowledge_base_documents',
        sa.Column('metadata_value', sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('knowledge_base_documents', 'metadata_value')
