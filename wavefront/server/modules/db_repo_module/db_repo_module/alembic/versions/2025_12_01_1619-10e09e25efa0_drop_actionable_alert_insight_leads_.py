"""drop_actionable_alert_insight_leads_table

Revision ID: 10e09e25efa0
Revises: ca83b60258d6
Create Date: 2025-12-01 16:19:58.228914

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '10e09e25efa0'
down_revision: Union[str, None] = 'ca83b60258d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the three tables
    op.drop_table('actionable_alerts')
    op.drop_table('actionable_insight_queries')
    op.drop_table('leads')


def downgrade() -> None:
    # Recreate leads table
    op.create_table(
        'leads',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('product_category', sa.String(), nullable=True),
        sa.Column('conversation_id', sa.String(), nullable=True),
        sa.Column('customer_id', sa.String(), nullable=True),
        sa.Column('agent_id', sa.String(), nullable=True),
        sa.Column('branch', sa.String(), nullable=True),
        sa.Column('region', sa.String(), nullable=True),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('product_name', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    # Recreate actionable_insight_queries table
    op.create_table(
        'actionable_insight_queries',
        sa.Column('id', sa.String(length=255), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('periodicity', sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column('goal_lines', sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column('projections', sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column('query', sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column('plots', sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column(
            'updated_at',
            sa.DateTime(),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint('id'),
    )

    # Recreate actionable_alerts table
    op.create_table(
        'actionable_alerts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('signal_id', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('signal_type', sa.String(), nullable=False),
        sa.Column('signal_name', sa.String(), nullable=True),
        sa.Column('alerts', sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column('data', sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint('id'),
    )
