"""create chatbot tables

Revision ID: e5b1d84c2f09
Revises: a3e7c91d4b26
Create Date: 2026-09-17 12:00:00.000000

Adds the text chatbot feature: `chatbots` holds a system prompt bound to an LLM
config, `chat_sessions` is one user's thread against one chatbot, and
`chat_messages` holds the turns.

Messages are rows rather than a JSONB array on the session: appending to a JSONB
array rewrites the whole TOASTed value on every turn, loses concurrent writes,
and cannot be paginated.

`chat_messages` has no sequence column -- ordering is `created_at`, which is
written Python-side (not `now()`) and, per the send flow, in a separate
transaction from the preceding user message so the two never collide.

`chat_sessions.chatbot_id` is deliberately not ON DELETE CASCADE: chatbot
deletion is soft, so threads must outlive it. `chat_messages.session_id` is,
because a hard-deleted session's turns are worthless.

Index note: every foreign key is indexed, but where a composite index already
leads with the FK column that composite IS the FK index -- `chat_sessions.user_id`
and `chat_messages.session_id` are covered by their composites below. A
single-column duplicate would only add write cost.

Additive only -- no existing table is touched.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e5b1d84c2f09'
down_revision: Union[str, None] = 'a3e7c91d4b26'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'chatbots',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('namespace', sa.String(length=255), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('system_prompt', sa.Text(), nullable=False),
        sa.Column('welcome_message', sa.Text(), nullable=True),
        sa.Column('llm_config_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('config', postgresql.JSONB(), nullable=True),
        sa.Column(
            'enabled',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('false'),
        ),
        sa.Column(
            'is_deleted',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('false'),
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
        sa.ForeignKeyConstraint(['namespace'], ['namespaces.name']),
        sa.ForeignKeyConstraint(['llm_config_id'], ['llm_inference_config.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('namespace', 'name', name='uq_chatbots_namespace_name'),
    )
    op.create_index(op.f('ix_chatbots_id'), 'chatbots', ['id'], unique=False)
    op.create_index(
        op.f('ix_chatbots_namespace'), 'chatbots', ['namespace'], unique=False
    )
    op.create_index(
        op.f('ix_chatbots_llm_config_id'), 'chatbots', ['llm_config_id'], unique=False
    )

    op.create_table(
        'chat_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('chatbot_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=True),
        sa.Column('system_prompt_snapshot', sa.Text(), nullable=False),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        sa.Column(
            'is_deleted',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('false'),
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
        sa.ForeignKeyConstraint(['chatbot_id'], ['chatbots.id']),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_chat_sessions_id'), 'chat_sessions', ['id'], unique=False)
    op.create_index(
        op.f('ix_chat_sessions_chatbot_id'),
        'chat_sessions',
        ['chatbot_id'],
        unique=False,
    )
    # Covers the user_id FK and "my sessions, newest first" in one index.
    op.create_index(
        'ix_chat_sessions_user_id_created_at',
        'chat_sessions',
        ['user_id', sa.text('created_at DESC')],
        unique=False,
    )

    op.create_table(
        'chat_messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role', sa.String(length=32), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        # No server_default: created_at is supplied per row by the application so
        # that two rows written in one transaction cannot share a timestamp.
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['session_id'], ['chat_sessions.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_chat_messages_id'), 'chat_messages', ['id'], unique=False)
    # Covers the session_id FK and every history read in one index.
    op.create_index(
        'ix_chat_messages_session_id_created_at',
        'chat_messages',
        ['session_id', 'created_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_chat_messages_session_id_created_at', table_name='chat_messages')
    op.drop_index(op.f('ix_chat_messages_id'), table_name='chat_messages')
    op.drop_table('chat_messages')

    op.drop_index('ix_chat_sessions_user_id_created_at', table_name='chat_sessions')
    op.drop_index(op.f('ix_chat_sessions_chatbot_id'), table_name='chat_sessions')
    op.drop_index(op.f('ix_chat_sessions_id'), table_name='chat_sessions')
    op.drop_table('chat_sessions')

    op.drop_index(op.f('ix_chatbots_llm_config_id'), table_name='chatbots')
    op.drop_index(op.f('ix_chatbots_namespace'), table_name='chatbots')
    op.drop_index(op.f('ix_chatbots_id'), table_name='chatbots')
    op.drop_table('chatbots')
