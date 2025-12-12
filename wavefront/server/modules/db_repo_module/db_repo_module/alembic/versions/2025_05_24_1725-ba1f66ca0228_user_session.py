"""user-session

Revision ID: ba1f66ca0228
Revises: 80a6b1232d5e
Create Date: 2025-05-24 17:25:58.041570

"""

from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'ba1f66ca0228'
down_revision: Union[str, None] = '80a6b1232d5e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'user_session',
        sa.Column('id', sa.UUID(), nullable=False, default=uuid.uuid4),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('device_info', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.Column(
            'updated_at',
            sa.DateTime(),
            nullable=False,
            default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_user_session_id'), 'user_session', ['id'], unique=False)
    op.create_index(
        op.f('ix_user_session_user_id'), 'user_session', ['user_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_user_session_user_id'), table_name='user_session')
    op.drop_index(op.f('ix_user_session_id'), table_name='user_session')
    op.drop_table('user_session')
