"""add last_login_at to user table

Revision ID: 1aaf2b1e6d56
Revises: d5caffc321f2
Create Date: 2025-08-14 14:55:39.364897

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1aaf2b1e6d56'
down_revision: Union[str, None] = 'd5caffc321f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add last_login_at field to user table
    op.add_column('user', sa.Column('last_login_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    # Remove last_login_at field from user table
    op.drop_column('user', 'last_login_at')
