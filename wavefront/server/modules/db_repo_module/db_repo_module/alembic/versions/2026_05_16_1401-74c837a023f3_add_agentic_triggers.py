"""add agentic triggers

Revision ID: 74c837a023f3
Revises: b2c3d4e5f6a0
Create Date: 2026-05-16 14:01:11.712250

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '74c837a023f3'
down_revision: Union[str, None] = 'b2c3d4e5f6a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'agentic_trigger_credentials',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            'provider',
            sa.String(length=32),
            nullable=False,
            comment='possible values: gmail',
        ),
        sa.Column('external_account_id', sa.String(length=320), nullable=False),
        sa.Column('encrypted_refresh_token', sa.Text(), nullable=False),
        sa.Column('encrypted_access_token', sa.Text(), nullable=True),
        sa.Column('token_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('scopes', sa.Text(), nullable=True),
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
        sa.UniqueConstraint(
            'provider',
            'external_account_id',
            name='uq_trigger_credential_account',
        ),
    )
    op.create_index(
        op.f('ix_agentic_trigger_credentials_id'),
        'agentic_trigger_credentials',
        ['id'],
        unique=False,
    )
    op.create_index(
        'ix_agentic_trigger_credentials_provider',
        'agentic_trigger_credentials',
        ['provider'],
        unique=False,
    )
    op.create_index(
        'ix_agentic_trigger_credentials_external_account_id',
        'agentic_trigger_credentials',
        ['external_account_id'],
        unique=False,
    )

    op.create_table(
        'agentic_triggers',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column(
            'provider',
            sa.String(length=32),
            nullable=False,
            comment='possible values: gmail',
        ),
        sa.Column(
            'entity_type',
            sa.String(length=32),
            nullable=False,
            comment='possible values: agent, workflow',
        ),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('namespace', sa.String(length=255), nullable=True),
        sa.Column(
            'status',
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'pending_auth'"),
            comment=('possible values: pending_auth, active, paused, error, deleted'),
        ),
        sa.Column(
            'filter_config', postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column(
            'provider_config',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column('credential_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
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
            ['credential_id'],
            ['agentic_trigger_credentials.id'],
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_agentic_triggers_id'),
        'agentic_triggers',
        ['id'],
        unique=False,
    )
    op.create_index(
        'ix_agentic_triggers_provider',
        'agentic_triggers',
        ['provider'],
        unique=False,
    )
    op.create_index(
        'ix_agentic_triggers_entity_id',
        'agentic_triggers',
        ['entity_id'],
        unique=False,
    )
    op.create_index(
        'ix_agentic_triggers_status',
        'agentic_triggers',
        ['status'],
        unique=False,
    )
    op.create_index(
        'ix_agentic_triggers_credential_id',
        'agentic_triggers',
        ['credential_id'],
        unique=False,
    )

    op.create_table(
        'agentic_trigger_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('trigger_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('provider_event_id', sa.String(length=255), nullable=False),
        sa.Column(
            'status',
            sa.String(length=32),
            nullable=False,
            comment=('possible values: received, filtered_out, dispatched, failed'),
        ),
        sa.Column('execution_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('subject', sa.String(length=1024), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column(
            'received_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
        ),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ['trigger_id'], ['agentic_triggers.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'trigger_id',
            'provider_event_id',
            name='uq_trigger_event_provider_id',
        ),
    )
    op.create_index(
        op.f('ix_agentic_trigger_events_id'),
        'agentic_trigger_events',
        ['id'],
        unique=False,
    )
    op.create_index(
        'ix_agentic_trigger_events_trigger_id',
        'agentic_trigger_events',
        ['trigger_id'],
        unique=False,
    )
    op.create_index(
        'ix_agentic_trigger_events_status',
        'agentic_trigger_events',
        ['status'],
        unique=False,
    )
    op.create_index(
        'ix_agentic_trigger_events_execution_id',
        'agentic_trigger_events',
        ['execution_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        'ix_agentic_trigger_events_execution_id',
        table_name='agentic_trigger_events',
    )
    op.drop_index(
        'ix_agentic_trigger_events_status',
        table_name='agentic_trigger_events',
    )
    op.drop_index(
        'ix_agentic_trigger_events_trigger_id',
        table_name='agentic_trigger_events',
    )
    op.drop_index(
        op.f('ix_agentic_trigger_events_id'),
        table_name='agentic_trigger_events',
    )
    op.drop_table('agentic_trigger_events')

    op.drop_index('ix_agentic_triggers_credential_id', table_name='agentic_triggers')
    op.drop_index('ix_agentic_triggers_status', table_name='agentic_triggers')
    op.drop_index('ix_agentic_triggers_entity_id', table_name='agentic_triggers')
    op.drop_index('ix_agentic_triggers_provider', table_name='agentic_triggers')
    op.drop_index(op.f('ix_agentic_triggers_id'), table_name='agentic_triggers')
    op.drop_table('agentic_triggers')

    op.drop_index(
        'ix_agentic_trigger_credentials_external_account_id',
        table_name='agentic_trigger_credentials',
    )
    op.drop_index(
        'ix_agentic_trigger_credentials_provider',
        table_name='agentic_trigger_credentials',
    )
    op.drop_index(
        op.f('ix_agentic_trigger_credentials_id'),
        table_name='agentic_trigger_credentials',
    )
    op.drop_table('agentic_trigger_credentials')
