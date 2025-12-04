"""Add message processor table

Revision ID: af9dfcda24fb
Revises: ed9fca299c85
Create Date: 2025-11-19 15:15:34.241072

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

# revision identifiers, used by Alembic.
revision: str = 'af9dfcda24fb'
down_revision: Union[str, None] = 'ed9fca299c85'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create message_processors table
    op.create_table(
        'message_processors',
        sa.Column(
            'id', postgresql.UUID(as_uuid=True), nullable=False, default=uuid.uuid4
        ),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('source', sa.String(length=512), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')
        ),
        sa.Column(
            'updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
        sa.UniqueConstraint('source'),
    )
    op.create_index(
        op.f('ix_message_processors_id'), 'message_processors', ['id'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_message_processors_id'), table_name='message_processors')
    op.drop_table('message_processors')
