"""chatbot_agent_reference

Revision ID: a4d9e17b3c52
Revises: e2a7c5d81f94
Create Date: 2026-10-10 12:00:00.000000

Lets a chatbot be backed by an agent instead of its own prompt and model.

Additive: existing rows keep their prompt and LLM config and are unaffected.
`system_prompt` and `llm_config_id` become nullable because an agent-backed
chatbot has neither. `agent_id` carries no foreign key on purpose; see the
column comment on the Chatbot model.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a4d9e17b3c52'
down_revision: Union[str, None] = 'e2a7c5d81f94'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'chatbots',
        sa.Column('agent_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        'chatbots',
        sa.Column('agent_version', sa.Integer(), nullable=True),
    )
    op.create_index('ix_chatbots_agent_id', 'chatbots', ['agent_id'])
    op.alter_column('chatbots', 'system_prompt', existing_type=sa.Text(), nullable=True)
    op.alter_column(
        'chatbots',
        'llm_config_id',
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )


def downgrade() -> None:
    # Agent-backed chatbots have no prompt or LLM config to fall back on, so
    # they cannot exist in the old shape. Their sessions go with them (the
    # messages cascade from the sessions).
    op.execute(
        """
        DELETE FROM chat_sessions
        WHERE chatbot_id IN (SELECT id FROM chatbots WHERE agent_id IS NOT NULL)
        """
    )
    op.execute('DELETE FROM chatbots WHERE agent_id IS NOT NULL')
    op.alter_column(
        'chatbots',
        'llm_config_id',
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.alter_column(
        'chatbots', 'system_prompt', existing_type=sa.Text(), nullable=False
    )
    op.drop_index('ix_chatbots_agent_id', table_name='chatbots')
    op.drop_column('chatbots', 'agent_version')
    op.drop_column('chatbots', 'agent_id')
