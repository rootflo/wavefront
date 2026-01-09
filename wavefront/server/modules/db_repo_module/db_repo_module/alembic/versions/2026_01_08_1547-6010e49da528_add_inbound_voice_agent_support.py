"""add_inbound_voice_agent_support

Revision ID: 6010e49da528
Revises: f7572bcd9510
Create Date: 2026-01-08 15:47:54.502531

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '6010e49da528'
down_revision: Union[str, None] = 'f7572bcd9510'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns to voice_agents table (initially nullable)
    op.add_column(
        'voice_agents',
        sa.Column(
            'inbound_numbers', postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )
    op.add_column(
        'voice_agents',
        sa.Column(
            'outbound_numbers', postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )
    op.add_column(
        'voice_agents',
        sa.Column(
            'supported_languages',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        'voice_agents',
        sa.Column('default_language', sa.String(length=10), nullable=True),
    )

    # Set defaults for existing agents
    op.execute("""
        UPDATE voice_agents
        SET
            inbound_numbers = '[]'::jsonb,
            outbound_numbers = '[]'::jsonb,
            supported_languages = '["en"]'::jsonb,
            default_language = 'en'
        WHERE inbound_numbers IS NULL
    """)

    # Make columns non-nullable after setting defaults
    op.alter_column('voice_agents', 'inbound_numbers', nullable=False)
    op.alter_column('voice_agents', 'outbound_numbers', nullable=False)
    op.alter_column('voice_agents', 'supported_languages', nullable=False)
    op.alter_column('voice_agents', 'default_language', nullable=False)

    # Create GIN index for fast inbound number lookups (JSONB containment queries)
    op.execute("""
        CREATE INDEX idx_voice_agents_inbound_numbers_gin
        ON voice_agents USING gin (inbound_numbers jsonb_path_ops)
    """)

    # Remove phone_numbers column from telephony_configs table
    # Phone numbers are now managed at the voice_agent level
    op.drop_column('telephony_configs', 'phone_numbers')


def downgrade() -> None:
    # Restore phone_numbers column to telephony_configs table
    op.add_column(
        'telephony_configs', sa.Column('phone_numbers', sa.Text(), nullable=True)
    )

    # Drop GIN index
    op.drop_index('idx_voice_agents_inbound_numbers_gin', table_name='voice_agents')

    # Drop columns from voice_agents
    op.drop_column('voice_agents', 'default_language')
    op.drop_column('voice_agents', 'supported_languages')
    op.drop_column('voice_agents', 'outbound_numbers')
    op.drop_column('voice_agents', 'inbound_numbers')
