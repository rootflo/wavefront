"""drop knowledge_base_inferences

Revision ID: e2a7c5d81f94
Revises: d1f6a8b3c247
Create Date: 2026-10-03 16:00:00.000000

Knowledge base "inferences" (a stored system prompt + LLM config per KB, used
by /v1/knowledge-base/{kb_id}/augment and the querying_knowlegebase agent
tool) are removed; RAG over a knowledge base goes through the chatbot feature
instead. The stored prompts are deleted with the table.

Downgrade recreates the empty table as it was (including config_id and its
foreign key); the deleted rows are not restored.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e2a7c5d81f94'
down_revision: Union[str, None] = 'd1f6a8b3c247'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table('knowledge_base_inferences')


def downgrade() -> None:
    op.create_table(
        'knowledge_base_inferences',
        sa.Column('inference_id', sa.Uuid(), nullable=False),
        sa.Column('knowledge_base_id', sa.Uuid(), nullable=False),
        sa.Column('inference_content', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('config_id', sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ['knowledge_base_id'], ['knowledge_bases.id'], ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['config_id'],
            ['llm_inference_config.id'],
            name='fk_kb_inferences_config_id',
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('inference_id'),
    )
    op.create_index(
        op.f('ix_knowledge_base_inferences_inference_id'),
        'knowledge_base_inferences',
        ['inference_id'],
        unique=False,
    )
