"""create scheduled jobs tables

Revision ID: c7a9e2f4b1d0
Revises: c153b06cfe7f
Create Date: 2026-03-24 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c7a9e2f4b1d0'
down_revision: Union[str, None] = 'c153b06cfe7f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'scheduled_job',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('job_type', sa.String(length=64), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('cron_expr', sa.String(length=64), nullable=False),
        sa.Column(
            'timezone',
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("'UTC'"),
        ),
        sa.Column(
            'status',
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column('next_run_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.String(), nullable=True),
        sa.Column(
            'retry_count', sa.Integer(), nullable=False, server_default=sa.text('0')
        ),
        sa.Column(
            'max_retries', sa.Integer(), nullable=False, server_default=sa.text('3')
        ),
        sa.Column('locked_by', sa.String(length=128), nullable=True),
        sa.Column('locked_at', sa.DateTime(timezone=True), nullable=True),
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
    op.create_index(op.f('ix_scheduled_job_id'), 'scheduled_job', ['id'], unique=False)
    op.create_index(
        'ix_scheduled_job_due_lookup',
        'scheduled_job',
        ['status', 'next_run_at'],
        unique=False,
    )

    op.create_table(
        'scheduled_job_execution',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('scheduled_job_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('execution_key', sa.String(length=128), nullable=False),
        sa.Column('scheduled_for', sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            'status',
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'running'"),
        ),
        sa.Column('error', sa.String(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ['scheduled_job_id'],
            ['scheduled_job.id'],
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'scheduled_job_id',
            'scheduled_for',
            name='uq_scheduled_job_execution_job_time',
        ),
    )
    op.create_index(
        op.f('ix_scheduled_job_execution_id'),
        'scheduled_job_execution',
        ['id'],
        unique=False,
    )
    op.create_index(
        'ix_scheduled_job_execution_key',
        'scheduled_job_execution',
        ['execution_key'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        'ix_scheduled_job_execution_key', table_name='scheduled_job_execution'
    )
    op.drop_index(
        op.f('ix_scheduled_job_execution_id'), table_name='scheduled_job_execution'
    )
    op.drop_table('scheduled_job_execution')

    op.drop_index('ix_scheduled_job_due_lookup', table_name='scheduled_job')
    op.drop_index(op.f('ix_scheduled_job_id'), table_name='scheduled_job')
    op.drop_table('scheduled_job')
