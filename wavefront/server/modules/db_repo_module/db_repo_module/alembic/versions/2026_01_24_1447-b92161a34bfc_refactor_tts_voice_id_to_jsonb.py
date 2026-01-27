"""refactor_tts_voice_ids_to_jsonb

Revision ID: b92161a34bfc
Revises: a5b3c4d5e6f7
Create Date: 2026-01-24 14:47:58.115161

"""

from typing import Sequence, Union
import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'b92161a34bfc'
down_revision: Union[str, None] = 'a5b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Convert tts_voice_id from String to tts_voice_ids JSONB dictionary.

    For each agent, converts the single voice ID string to a dictionary
    mapping each supported language to that voice ID.

    Example: "alloy" with supported_languages=["en", "hi"] becomes {"en": "alloy", "hi": "alloy"}
    """
    connection = op.get_bind()

    # Step 1: Add new JSONB column (nullable initially)
    op.execute("""
        ALTER TABLE voice_agents
        ADD COLUMN IF NOT EXISTS tts_voice_ids JSONB
    """)

    # Step 2: Migrate data - convert string to dict for all supported_languages
    # Note: Migrate ALL agents including deleted ones to avoid NOT NULL constraint violation
    agents = connection.execute(
        text("""
        SELECT id, tts_voice_id, supported_languages
        FROM voice_agents
    """)
    ).fetchall()

    for agent in agents:
        old_voice_id = agent.tts_voice_id

        # Handle null/empty supported_languages - default to ["en"]
        if agent.supported_languages:
            if isinstance(agent.supported_languages, list):
                supported_langs = agent.supported_languages
            else:
                # In case it's stored as JSON string
                try:
                    supported_langs = json.loads(agent.supported_languages)
                except (json.JSONDecodeError, TypeError):
                    supported_langs = ['en']
        else:
            supported_langs = ['en']

        # Build dict: apply old voice_id to all supported languages
        voice_ids_dict = {lang: old_voice_id for lang in supported_langs}

        # Update the agent with new JSONB dict
        connection.execute(
            text("""
            UPDATE voice_agents
            SET tts_voice_ids = :voice_dict
            WHERE id = :agent_id
        """),
            {'voice_dict': json.dumps(voice_ids_dict), 'agent_id': str(agent.id)},
        )

    # Step 3: Make new column NOT NULL
    op.execute("""
        ALTER TABLE voice_agents
        ALTER COLUMN tts_voice_ids SET NOT NULL
    """)

    # Step 4: Drop old column
    op.execute("""
        ALTER TABLE voice_agents
        DROP COLUMN tts_voice_id
    """)


def downgrade() -> None:
    """
    Restore tts_voice_id as String column from tts_voice_ids JSONB.

    This is a lossy operation - only the voice ID for the default_language
    is preserved. Voice IDs for other languages are lost.
    """
    connection = op.get_bind()

    # Step 1: Add old string column back (nullable initially)
    op.add_column(
        'voice_agents', sa.Column('tts_voice_id', sa.String(255), nullable=True)
    )

    # Step 2: Extract voice_id from dict (use default_language voice or first available)
    agents = connection.execute(
        text("""
        SELECT id, tts_voice_ids, default_language
        FROM voice_agents
    """)
    ).fetchall()

    for agent in agents:
        # Parse JSONB dict
        if agent.tts_voice_ids:
            if isinstance(agent.tts_voice_ids, dict):
                voice_dict = agent.tts_voice_ids
            else:
                try:
                    voice_dict = json.loads(agent.tts_voice_ids)
                except (json.JSONDecodeError, TypeError):
                    voice_dict = {}
        else:
            voice_dict = {}

        # Try to use default_language voice, fallback to first available, or 'default'
        default_lang = agent.default_language or 'en'
        voice_id = voice_dict.get(default_lang) or next(
            iter(voice_dict.values()), 'default'
        )

        # Update with single voice_id string
        connection.execute(
            text("""
            UPDATE voice_agents
            SET tts_voice_id = :voice_id
            WHERE id = :agent_id
        """),
            {'voice_id': voice_id, 'agent_id': str(agent.id)},
        )

    # Step 3: Make old column NOT NULL
    op.execute("""
        ALTER TABLE voice_agents
        ALTER COLUMN tts_voice_id SET NOT NULL
    """)

    # Step 4: Drop JSONB column
    op.drop_column('voice_agents', 'tts_voice_ids')
