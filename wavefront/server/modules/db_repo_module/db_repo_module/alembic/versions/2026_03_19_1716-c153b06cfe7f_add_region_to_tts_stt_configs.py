"""add_region_to_tts_stt_configs

Revision ID: c153b06cfe7f
Revises: b92161a34bfc
Create Date: 2026-03-19 17:16:45.273180

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c153b06cfe7f'
down_revision: Union[str, None] = 'b92161a34bfc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'tts_configs', sa.Column('region', sa.String(length=64), nullable=True)
    )
    op.add_column(
        'stt_configs', sa.Column('region', sa.String(length=64), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('stt_configs', 'region')
    op.drop_column('tts_configs', 'region')
