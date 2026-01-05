"""embedding_models

Revision ID: f7572bcd9510
Revises: 10e09e25efa0
Create Date: 2025-12-16 14:06:06.178161

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7572bcd9510'
down_revision: Union[str, None] = '10e09e25efa0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add model_type column to llm_inference_config table
    # Set default to 'llm' for all existing rows
    op.add_column(
        'llm_inference_config',
        sa.Column(
            'model_type', sa.String(length=64), nullable=False, server_default='llm'
        ),
    )


def downgrade() -> None:
    # Remove model_type column from llm_inference_config table
    op.drop_column('llm_inference_config', 'model_type')
