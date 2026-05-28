"""add_inbound_voice_agent_support_and_refactor_tts_stt

Revision ID: 6010e49da528
Revises: f7572bcd9510
Create Date: 2026-01-08 15:47:54.502531

"""

import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = '6010e49da528'
down_revision: Union[str, None] = 'f7572bcd9510'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns to voice_agents table (initially nullable)
    # Use raw SQL with IF NOT EXISTS for idempotency
    op.execute("""
        ALTER TABLE voice_agents
        ADD COLUMN IF NOT EXISTS inbound_numbers JSONB,
        ADD COLUMN IF NOT EXISTS outbound_numbers JSONB,
        ADD COLUMN IF NOT EXISTS supported_languages JSONB,
        ADD COLUMN IF NOT EXISTS default_language VARCHAR(10),
        ADD COLUMN IF NOT EXISTS tts_voice_id VARCHAR(255),
        ADD COLUMN IF NOT EXISTS tts_parameters JSONB,
        ADD COLUMN IF NOT EXISTS stt_parameters JSONB
    """)

    # Set defaults for existing agents
    op.execute("""
        UPDATE voice_agents
        SET
            inbound_numbers = COALESCE(inbound_numbers, '[]'::jsonb),
            outbound_numbers = COALESCE(outbound_numbers, '[]'::jsonb),
            supported_languages = COALESCE(supported_languages, '["en"]'::jsonb),
            default_language = COALESCE(default_language, 'en')
        WHERE inbound_numbers IS NULL
           OR outbound_numbers IS NULL
           OR supported_languages IS NULL
           OR default_language IS NULL
    """)

    # Migrate TTS/STT data from configs to voice_agents
    connection = op.get_bind()

    # Fetch all non-deleted voice agents with their TTS/STT configs (using LEFT JOINs)
    agents = connection.execute(
        text("""
        SELECT
            va.id as agent_id,
            tc.voice_id as tts_voice_id,
            tc.parameters as tts_params,
            sc.parameters as stt_params
        FROM voice_agents va
        LEFT JOIN tts_configs tc ON va.tts_config_id = tc.id
        LEFT JOIN stt_configs sc ON va.stt_config_id = sc.id
        WHERE va.is_deleted = false
    """)
    ).fetchall()

    # Migrate data for each agent
    for agent in agents:
        # Parse JSON parameters (may be None)
        tts_params_dict = json.loads(agent.tts_params) if agent.tts_params else {}
        stt_params_dict = json.loads(agent.stt_params) if agent.stt_params else {}

        # Use default voice_id if not available
        tts_voice_id = agent.tts_voice_id if agent.tts_voice_id else 'default'

        # Update agent with TTS/STT data
        connection.execute(
            text("""
            UPDATE voice_agents
            SET
                tts_voice_id = :voice_id,
                tts_parameters = :tts_params,
                stt_parameters = :stt_params
            WHERE id = :agent_id
        """),
            {
                'voice_id': tts_voice_id,
                'tts_params': json.dumps(tts_params_dict),
                'stt_params': json.dumps(stt_params_dict),
                'agent_id': str(agent.agent_id),
            },
        )

    # Safety check: Set default tts_voice_id for any remaining NULL values
    # This handles cases where agents don't have associated configs or were missed
    op.execute("""
        UPDATE voice_agents
        SET tts_voice_id = 'default'
        WHERE tts_voice_id IS NULL
    """)

    # Make columns non-nullable after setting defaults (idempotent)
    connection = op.get_bind()

    # Only alter if currently nullable
    for col in [
        'inbound_numbers',
        'outbound_numbers',
        'supported_languages',
        'default_language',
        'tts_voice_id',
    ]:
        result = connection.execute(
            text(f"""
            SELECT is_nullable FROM information_schema.columns
            WHERE table_name = 'voice_agents' AND column_name = '{col}'
        """)
        )
        row = result.fetchone()
        if row and row[0] == 'YES':
            connection.execute(
                text(f'ALTER TABLE voice_agents ALTER COLUMN {col} SET NOT NULL')
            )

    # Remove phone_numbers column from telephony_configs table
    # Phone numbers are now managed at the voice_agent level
    # Use conditional drop to make it idempotent
    op.execute("""
        ALTER TABLE telephony_configs
        DROP COLUMN IF EXISTS phone_numbers
    """)

    # Remove provider-specific columns from tts_configs
    # These are now stored in voice_agents
    op.execute("""
        ALTER TABLE tts_configs
        DROP COLUMN IF EXISTS voice_id,
        DROP COLUMN IF EXISTS language,
        DROP COLUMN IF EXISTS parameters
    """)

    # Remove provider-specific columns from stt_configs
    op.execute("""
        ALTER TABLE stt_configs
        DROP COLUMN IF EXISTS language,
        DROP COLUMN IF EXISTS parameters
    """)


def downgrade() -> None:
    # Restore phone_numbers column to telephony_configs table (won't restore data)
    op.add_column(
        'telephony_configs', sa.Column('phone_numbers', sa.Text(), nullable=True)
    )

    # Restore TTS/STT config columns
    op.add_column(
        'tts_configs', sa.Column('voice_id', sa.String(length=255), nullable=True)
    )
    op.add_column(
        'tts_configs', sa.Column('language', sa.String(length=64), nullable=True)
    )
    op.add_column('tts_configs', sa.Column('parameters', sa.Text(), nullable=True))
    op.add_column(
        'stt_configs', sa.Column('language', sa.String(length=64), nullable=True)
    )
    op.add_column('stt_configs', sa.Column('parameters', sa.Text(), nullable=True))

    # Drop columns from voice_agents
    op.drop_column('voice_agents', 'default_language')
    op.drop_column('voice_agents', 'supported_languages')
    op.drop_column('voice_agents', 'outbound_numbers')
    op.drop_column('voice_agents', 'inbound_numbers')
    op.drop_column('voice_agents', 'stt_parameters')
    op.drop_column('voice_agents', 'tts_parameters')
    op.drop_column('voice_agents', 'tts_voice_id')
