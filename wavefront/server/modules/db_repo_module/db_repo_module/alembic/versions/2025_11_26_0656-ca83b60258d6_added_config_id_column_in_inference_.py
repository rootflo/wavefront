"""Added config_id column in inference table

Revision ID: ca83b60258d6
Revises: a9a5d624020c
Create Date: 2025-11-26 06:56:44.540145

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'ca83b60258d6'
down_revision: Union[str, None] = 'a9a5d624020c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'knowledge_base_inferences',
        sa.Column('config_id', sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        'fk_kb_inferences_config_id',
        'knowledge_base_inferences',
        'llm_inference_config',
        ['config_id'],
        ['id'],
        ondelete='CASCADE',
    )


def downgrade() -> None:
    op.drop_constraint(
        'fk_kb_inferences_config_id',
        'knowledge_base_inferences',
        type_='foreignkey',
    )
    op.drop_column('knowledge_base_inferences', 'config_id')
