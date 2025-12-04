"""add account lockout fields to user table

Revision ID: 1ef7d577ea53
Revises: 68ffaa4a3665
Create Date: 2025-08-13 13:09:27.095292

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1ef7d577ea53'
down_revision: Union[str, None] = '68ffaa4a3665'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add account lockout fields to user table
    # First add as nullable with server default
    op.add_column(
        'user',
        sa.Column('failed_attempts', sa.Integer(), nullable=True, server_default='0'),
    )
    op.add_column('user', sa.Column('locked_until', sa.DateTime(), nullable=True))
    op.add_column(
        'user', sa.Column('last_failed_attempt', sa.DateTime(), nullable=True)
    )

    # Update existing records to have failed_attempts = 0
    op.execute('UPDATE "user" SET failed_attempts = 0 WHERE failed_attempts IS NULL')

    # Now make failed_attempts non-nullable with default value
    op.alter_column('user', 'failed_attempts', nullable=False, server_default='0')


def downgrade() -> None:
    # Remove account lockout fields from user table
    op.drop_column('user', 'last_failed_attempt')
    op.drop_column('user', 'locked_until')
    op.drop_column('user', 'failed_attempts')
