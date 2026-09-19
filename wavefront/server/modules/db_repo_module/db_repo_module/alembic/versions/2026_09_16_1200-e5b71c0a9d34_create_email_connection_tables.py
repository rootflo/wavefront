"""create email oauth app and email connection tables

Clean break from the old Gmail-only `agentic_trigger_credentials` path:
existing trigger credentials and triggers are discarded, not migrated. Admins
recreate OAuth apps and mailbox connections under the new model, then re-create
triggers against those connections.

Also drops two dead tables: `oauth_credential` and `email`.

Revision ID: e5b71c0a9d34
Revises: a3e7c91d4b26
Create Date: 2026-09-16 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'e5b71c0a9d34'
down_revision: Union[str, None] = 'e5b1d84c2f09'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'oauth_apps',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column(
            'provider',
            sa.String(length=32),
            nullable=False,
            comment='possible values: gmail, outlook',
        ),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('encrypted_client_secret', sa.Text(), nullable=False),
        sa.Column(
            'is_enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')
        ),
        sa.Column(
            'is_deleted', sa.Boolean(), nullable=False, server_default=sa.text('false')
        ),
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
        sa.UniqueConstraint('name', name='uq_oauth_app_name'),
        sa.CheckConstraint("name !~ '\\s'", name='oauth_app_name_no_spaces'),
    )
    op.create_index(op.f('ix_oauth_apps_id'), 'oauth_apps', ['id'], unique=False)
    op.create_index(
        'ix_oauth_apps_provider',
        'oauth_apps',
        ['provider'],
        unique=False,
    )

    op.create_table(
        'email_connections',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column(
            'provider',
            sa.String(length=32),
            nullable=False,
            comment='possible values: gmail, outlook',
        ),
        sa.Column('oauth_app_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('mailbox_email', sa.String(length=320), nullable=False),
        sa.Column(
            'status',
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'pending_auth'"),
            comment=('possible values: pending_auth, active, error, revoked, deleted'),
        ),
        sa.Column('granted_scopes', sa.Text(), nullable=True),
        sa.Column('encrypted_refresh_token', sa.Text(), nullable=True),
        sa.Column('encrypted_access_token', sa.Text(), nullable=True),
        sa.Column('token_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'is_primary', sa.Boolean(), nullable=False, server_default=sa.text('false')
        ),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(length=255), nullable=True),
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
            ['oauth_app_id'],
            ['oauth_apps.id'],
            ondelete='RESTRICT',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_email_connections_id'), 'email_connections', ['id'], unique=False
    )
    op.create_index(
        'ix_email_connections_provider',
        'email_connections',
        ['provider'],
        unique=False,
    )
    op.create_index(
        'ix_email_connections_oauth_app_id',
        'email_connections',
        ['oauth_app_id'],
        unique=False,
    )
    op.create_index(
        'ix_email_connections_mailbox_email',
        'email_connections',
        ['mailbox_email'],
        unique=False,
    )
    op.create_index(
        'ix_email_connections_status', 'email_connections', ['status'], unique=False
    )
    op.create_index(
        'uq_email_connection_mailbox',
        'email_connections',
        ['provider', 'mailbox_email'],
        unique=True,
        postgresql_where=sa.text("status <> 'deleted'"),
    )
    op.create_index(
        'uq_email_connection_primary',
        'email_connections',
        ['is_primary'],
        unique=True,
        postgresql_where=sa.text('is_primary'),
    )

    # Discard old Gmail trigger credentials and any triggers that used them.
    # Events cascade from triggers.
    op.execute('DELETE FROM agentic_triggers')

    op.drop_constraint(
        'agentic_triggers_credential_id_fkey',
        'agentic_triggers',
        type_='foreignkey',
    )
    op.drop_index('ix_agentic_triggers_credential_id', table_name='agentic_triggers')
    op.drop_column('agentic_triggers', 'credential_id')

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

    op.add_column(
        'agentic_triggers',
        sa.Column('connection_id', postgresql.UUID(as_uuid=True), nullable=False),
    )
    op.create_index(
        'ix_agentic_triggers_connection_id',
        'agentic_triggers',
        ['connection_id'],
        unique=False,
    )
    op.create_foreign_key(
        'fk_agentic_triggers_connection_id',
        'agentic_triggers',
        'email_connections',
        ['connection_id'],
        ['id'],
        ondelete='RESTRICT',
    )

    op.drop_table('oauth_credential')
    op.drop_table('email')


def downgrade() -> None:
    op.create_table(
        'email',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('thread_id', sa.String(), nullable=False),
        sa.Column('account_id', sa.String(), nullable=False),
        sa.Column('content', sa.String(), nullable=False),
        sa.Column('synced_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_email_id'), 'email', ['id'], unique=False)

    op.create_table(
        'oauth_credential',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('provider', sa.String(), nullable=False),
        sa.Column('access_token', sa.String(), nullable=False),
        sa.Column('refresh_token', sa.String(), nullable=False),
        sa.Column('token_uri', sa.String(), nullable=True),
        sa.Column('client_id', sa.String(), nullable=True),
        sa.Column('client_secret', sa.String(), nullable=True),
        sa.Column('scopes', sa.JSON(), nullable=False),
        sa.Column('expiry', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_oauth_credential_id'), 'oauth_credential', ['id'], unique=False
    )

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

    op.execute('DELETE FROM agentic_triggers')
    op.drop_constraint(
        'fk_agentic_triggers_connection_id', 'agentic_triggers', type_='foreignkey'
    )
    op.drop_index('ix_agentic_triggers_connection_id', table_name='agentic_triggers')
    op.drop_column('agentic_triggers', 'connection_id')

    op.add_column(
        'agentic_triggers',
        sa.Column('credential_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        'ix_agentic_triggers_credential_id',
        'agentic_triggers',
        ['credential_id'],
        unique=False,
    )
    op.create_foreign_key(
        None,
        'agentic_triggers',
        'agentic_trigger_credentials',
        ['credential_id'],
        ['id'],
        ondelete='SET NULL',
    )

    op.drop_index('uq_email_connection_primary', table_name='email_connections')
    op.drop_index('uq_email_connection_mailbox', table_name='email_connections')
    op.drop_index('ix_email_connections_status', table_name='email_connections')
    op.drop_index('ix_email_connections_mailbox_email', table_name='email_connections')
    op.drop_index('ix_email_connections_oauth_app_id', table_name='email_connections')
    op.drop_index('ix_email_connections_provider', table_name='email_connections')
    op.drop_index(op.f('ix_email_connections_id'), table_name='email_connections')
    op.drop_table('email_connections')

    op.drop_index('ix_oauth_apps_provider', table_name='oauth_apps')
    op.drop_index(op.f('ix_oauth_apps_id'), table_name='oauth_apps')
    op.drop_table('oauth_apps')
