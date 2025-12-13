"""adding notification

Revision ID: 78655faf6488
Revises: f9c4c1c48d46
Create Date: 2025-02-28 16:02:31.108730

"""

from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '78655faf6488'
down_revision: Union[str, None] = 'f9c4c1c48d46'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'notification',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('type', sa.String(), nullable=True),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )

    op.create_table(
        'notification_user',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('user_id', sa.UUID(), sa.ForeignKey('user.id'), nullable=False),
        sa.Column(
            'notification_id',
            sa.UUID(),
            sa.ForeignKey('notification.id'),
            nullable=False,
        ),
        sa.Column('seen', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_table('notification_user')
    op.drop_table('notification')
