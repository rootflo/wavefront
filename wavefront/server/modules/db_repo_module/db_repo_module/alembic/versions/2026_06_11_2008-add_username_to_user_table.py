"""add username to user table

Revision ID: a1b2c3d4e5f8
Revises: 74c837a023f3
Create Date: 2026-06-11 20:08:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f8'
down_revision: Union[str, None] = '74c837a023f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'user',
        sa.Column('username', sa.String(length=150), nullable=True),
    )
    op.create_unique_constraint('uq_user_username', 'user', ['username'])


def downgrade() -> None:
    op.drop_constraint('uq_user_username', 'user', type_='unique')
    op.drop_column('user', 'username')
