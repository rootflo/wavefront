"""create session table

Revision ID: e3a2fa91cda2
Revises: 73bcd253dd62
Create Date: 2025-08-18 15:43:35.644982

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e3a2fa91cda2'
down_revision = '73bcd253dd62'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'user_session',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('device_info', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
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
