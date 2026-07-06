"""add_async_agentic_executions

Revision ID: 3b5b1bf90e6c
Revises: e8f2a1c3b5d9
Create Date: 2026-05-12 15:49:11.063050

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '3b5b1bf90e6c'
down_revision: Union[str, None] = 'e8f2a1c3b5d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'async_agentic_executions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('entity_type', sa.String(length=32), nullable=False),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('celery_task_id', sa.String(length=255), nullable=True),
        sa.Column(
            'status',
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column('input_bucket', sa.String(length=255), nullable=True),
        sa.Column('inputs', sa.Text(), nullable=True),
        sa.Column('input_files', sa.Text(), nullable=True),
        sa.Column('output_file', sa.String(length=1024), nullable=True),
        sa.Column('history_file', sa.String(length=1024), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_async_agentic_executions_id'),
        'async_agentic_executions',
        ['id'],
        unique=False,
    )
    op.create_index(
        'ix_async_agentic_executions_entity_id',
        'async_agentic_executions',
        ['entity_id'],
        unique=False,
    )
    op.create_index(
        'ix_async_agentic_executions_entity_type',
        'async_agentic_executions',
        ['entity_type'],
        unique=False,
    )
    op.create_index(
        'ix_async_agentic_executions_status',
        'async_agentic_executions',
        ['status'],
        unique=False,
    )
    op.create_index(
        'ix_async_agentic_executions_entity_status',
        'async_agentic_executions',
        ['entity_id', 'entity_type', 'status'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        'ix_async_agentic_executions_entity_status',
        table_name='async_agentic_executions',
    )
    op.drop_index(
        'ix_async_agentic_executions_status', table_name='async_agentic_executions'
    )
    op.drop_index(
        'ix_async_agentic_executions_entity_type', table_name='async_agentic_executions'
    )
    op.drop_index(
        'ix_async_agentic_executions_entity_id', table_name='async_agentic_executions'
    )
    op.drop_index(
        op.f('ix_async_agentic_executions_id'), table_name='async_agentic_executions'
    )
    op.drop_table('async_agentic_executions')
