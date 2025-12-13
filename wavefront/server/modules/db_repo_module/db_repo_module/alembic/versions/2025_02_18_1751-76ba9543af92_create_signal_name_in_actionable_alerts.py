"""create signal name in actionable alerts

Revision ID: 76ba9543af92
Revises: c7800bd1d9c3
Create Date: 2025-02-18 17:51:32.463298

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '76ba9543af92'
down_revision: Union[str, None] = 'c7800bd1d9c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'actionable_alerts', sa.Column('signal_name', sa.String, nullable=True)
    )


def downgrade() -> None:
    op.drop_column('actionable_alerts', 'signal_name')
