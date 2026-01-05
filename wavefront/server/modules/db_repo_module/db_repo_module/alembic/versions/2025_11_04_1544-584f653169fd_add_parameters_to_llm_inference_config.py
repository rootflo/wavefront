"""voice_agents_and_llm_config_updates

This migration adds several enhancements to voice agent configuration and LLM inference:
1. Adds 'parameters' JSON column to llm_inference_config for flexible LLM parameters
2. Adds 'welcome_message' text column to voice_agents for storing greeting messages
3. Adds 'display_name' and 'description' fields to TTS, STT, and telephony configs

Revision ID: 584f653169fd
Revises: 9bd8b7884ab0
Create Date: 2025-11-04 15:44:13.442528

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '584f653169fd'
down_revision: Union[str, None] = '9bd8b7884ab0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add parameters column to llm_inference_config
    op.add_column(
        'llm_inference_config', sa.Column('parameters', sa.JSON(), nullable=True)
    )

    # Add welcome_message column to voice_agents
    op.add_column(
        'voice_agents',
        sa.Column('welcome_message', sa.Text(), nullable=False, server_default=''),
    )

    # Add display_name and description to tts_configs
    op.add_column(
        'tts_configs',
        sa.Column(
            'display_name', sa.String(length=100), nullable=False, server_default=''
        ),
    )
    op.add_column(
        'tts_configs', sa.Column('description', sa.String(length=500), nullable=True)
    )

    # Add display_name and description to stt_configs
    op.add_column(
        'stt_configs',
        sa.Column(
            'display_name', sa.String(length=100), nullable=False, server_default=''
        ),
    )
    op.add_column(
        'stt_configs', sa.Column('description', sa.String(length=500), nullable=True)
    )

    # Add display_name and description to telephony_configs
    op.add_column(
        'telephony_configs',
        sa.Column(
            'display_name', sa.String(length=100), nullable=False, server_default=''
        ),
    )
    op.add_column(
        'telephony_configs',
        sa.Column('description', sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    # Remove display_name and description from telephony_configs
    op.drop_column('telephony_configs', 'description')
    op.drop_column('telephony_configs', 'display_name')

    # Remove display_name and description from stt_configs
    op.drop_column('stt_configs', 'description')
    op.drop_column('stt_configs', 'display_name')

    # Remove display_name and description from tts_configs
    op.drop_column('tts_configs', 'description')
    op.drop_column('tts_configs', 'display_name')

    # Remove welcome_message from voice_agents
    op.drop_column('voice_agents', 'welcome_message')

    # Remove parameters from llm_inference_config
    op.drop_column('llm_inference_config', 'parameters')
