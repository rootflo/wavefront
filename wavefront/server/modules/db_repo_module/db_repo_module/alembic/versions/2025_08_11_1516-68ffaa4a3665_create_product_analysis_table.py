"""create product -analysis table

Revision ID: 68ffaa4a3665
Revises: a1b2c3d4e5f7
Create Date: 2025-08-11 15:16:09.245567

"""

from typing import Sequence, Union
import uuid
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '68ffaa4a3665'
down_revision: Union[str, None] = 'a1b2c3d4e5f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'product_analytics',
        sa.Column(
            'event_id', sa.UUID(), primary_key=True, nullable=False, default=uuid.uuid4
        ),
        sa.Column('event_name', sa.String(length=255), nullable=False),
        sa.Column('type', sa.String(length=255), nullable=True),
        sa.Column('sub_type', sa.String(length=255), nullable=True),
        sa.Column('category', sa.String(length=255), nullable=True),
        sa.Column('sub_category', sa.String(length=255), nullable=True),
        sa.Column('action', sa.String(length=255), nullable=True),
        sa.Column('action_type', sa.String(length=255), nullable=True),
        sa.Column('page', sa.String(length=255), nullable=False),
        sa.Column('page_path', sa.String(), nullable=False),
        sa.Column('matadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('user_id', sa.String(length=255), nullable=False),
        sa.Column('session_id', sa.String(), nullable=False),
        sa.Column('user_role', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('product_analytics')
