"""created actionable_insight_query table

Revision ID: ff32e2dd3106
Revises: 36703628c7a6
Create Date: 2025-04-22 14:48:12.819342

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'ff32e2dd3106'
down_revision: Union[str, None] = '36703628c7a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'actionable_insight_queries',
        sa.Column('id', sa.String(length=255), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column(
            'periodicity', postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            'goal_lines', postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            'projections', postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column('query', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('plots', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True
        ),
        sa.Column(
            'updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True
        ),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('actionable_insight_queries')
