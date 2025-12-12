"""create_voice_agents_tables

Revision ID: 22ec0134dcf8
Revises: 6742f38ca303
Create Date: 2025-10-29 13:46:33.854725

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '22ec0134dcf8'
down_revision: Union[str, None] = '6742f38ca303'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create telephony_configs table
    op.create_table(
        'telephony_configs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('provider', sa.String(length=64), nullable=False),
        sa.Column('connection_type', sa.String(length=64), nullable=False),
        sa.Column('credentials', sa.Text(), nullable=False),
        sa.Column('phone_numbers', sa.Text(), nullable=False),
        sa.Column('webhook_config', sa.Text(), nullable=True),
        sa.Column('sip_config', sa.Text(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column(
            'created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')
        ),
        sa.Column(
            'updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_telephony_configs_id'), 'telephony_configs', ['id'], unique=False
    )
    op.create_index(
        op.f('ix_telephony_configs_provider'),
        'telephony_configs',
        ['provider'],
        unique=False,
    )

    # Create tts_configs table
    op.create_table(
        'tts_configs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('provider', sa.String(length=64), nullable=False),
        sa.Column('voice_id', sa.String(length=255), nullable=False),
        sa.Column('api_key', sa.String(length=512), nullable=False),
        sa.Column('language', sa.String(length=64), nullable=True),
        sa.Column('parameters', sa.Text(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column(
            'created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')
        ),
        sa.Column(
            'updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_tts_configs_id'), 'tts_configs', ['id'], unique=False)
    op.create_index(
        op.f('ix_tts_configs_provider'), 'tts_configs', ['provider'], unique=False
    )

    # Create stt_configs table
    op.create_table(
        'stt_configs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('provider', sa.String(length=64), nullable=False),
        sa.Column('api_key', sa.String(length=512), nullable=False),
        sa.Column('language', sa.String(length=64), nullable=True),
        sa.Column('parameters', sa.Text(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column(
            'created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')
        ),
        sa.Column(
            'updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_stt_configs_id'), 'stt_configs', ['id'], unique=False)
    op.create_index(
        op.f('ix_stt_configs_provider'), 'stt_configs', ['provider'], unique=False
    )

    # Create voice_agents table (with foreign keys to the above tables)
    op.create_table(
        'voice_agents',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('llm_config_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tts_config_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('stt_config_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('telephony_config_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('system_prompt', sa.Text(), nullable=False),
        sa.Column('conversation_config', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=64), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column(
            'created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')
        ),
        sa.Column(
            'updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')
        ),
        sa.ForeignKeyConstraint(['llm_config_id'], ['llm_inference_config.id']),
        sa.ForeignKeyConstraint(['tts_config_id'], ['tts_configs.id']),
        sa.ForeignKeyConstraint(['stt_config_id'], ['stt_configs.id']),
        sa.ForeignKeyConstraint(['telephony_config_id'], ['telephony_configs.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_voice_agents_id'), 'voice_agents', ['id'], unique=False)
    op.create_index(
        op.f('ix_voice_agents_status'), 'voice_agents', ['status'], unique=False
    )


def downgrade() -> None:
    # Drop tables in reverse order (voice_agents first due to foreign key constraints)
    op.drop_index(op.f('ix_voice_agents_status'), table_name='voice_agents')
    op.drop_index(op.f('ix_voice_agents_id'), table_name='voice_agents')
    op.drop_table('voice_agents')

    op.drop_index(op.f('ix_stt_configs_provider'), table_name='stt_configs')
    op.drop_index(op.f('ix_stt_configs_id'), table_name='stt_configs')
    op.drop_table('stt_configs')

    op.drop_index(op.f('ix_tts_configs_provider'), table_name='tts_configs')
    op.drop_index(op.f('ix_tts_configs_id'), table_name='tts_configs')
    op.drop_table('tts_configs')

    op.drop_index(op.f('ix_telephony_configs_provider'), table_name='telephony_configs')
    op.drop_index(op.f('ix_telephony_configs_id'), table_name='telephony_configs')
    op.drop_table('telephony_configs')
