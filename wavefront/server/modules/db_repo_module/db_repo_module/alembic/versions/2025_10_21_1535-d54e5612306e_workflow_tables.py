"""Workflow tables

Revision ID: d54e5612306e
Revises: bf901c107c8d
Create Date: 2025-10-21 15:35:17.038431

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd54e5612306e'
down_revision: Union[str, None] = 'bf901c107c8d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create workflow_pipeline table
    op.create_table(
        'workflow_pipeline',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('location', sa.String(), nullable=False),
        sa.Column('retry_policy', sa.String(), nullable=True),
        sa.Column('timeout', sa.Integer(), nullable=True),
        sa.Column('concurrency_limit', sa.Integer(), nullable=True, default=1),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_workflow_pipeline_id'), 'workflow_pipeline', ['id'], unique=False
    )

    # Create workflow_runs table
    op.create_table(
        'workflow_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            'workflow_pipeline_id', postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('start_time', sa.DateTime(), nullable=False),
        sa.Column('end_time', sa.DateTime(), nullable=True),
        sa.Column('error', sa.String(), nullable=True),
        sa.Column('output', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ['workflow_pipeline_id'], ['workflow_pipeline.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_workflow_runs_id'), 'workflow_runs', ['id'], unique=False)


def downgrade() -> None:
    # Drop tables in reverse order (workflow_runs first due to foreign key constraint)
    op.drop_index(op.f('ix_workflow_runs_id'), table_name='workflow_runs')
    op.drop_table('workflow_runs')

    op.drop_index(op.f('ix_workflow_pipeline_id'), table_name='workflow_pipeline')
    op.drop_table('workflow_pipeline')
