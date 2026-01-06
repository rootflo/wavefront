"""create app_user table

Revision ID: 8d947e3f8ec6
Revises: 0644a81ee4e1
Create Date: 2026-01-06 16:46:18.673634

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8d947e3f8ec6'
down_revision = '0644a81ee4e1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'app_user',
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('app_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['app_id'], ['app.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id', 'app_id'),
    )

    # Add indexes for query performance
    op.create_index(op.f('ix_app_user_user_id'), 'app_user', ['user_id'], unique=False)
    op.create_index(op.f('ix_app_user_app_id'), 'app_user', ['app_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_app_user_app_id'), table_name='app_user')
    op.drop_index(op.f('ix_app_user_user_id'), table_name='app_user')
    op.drop_table('app_user')
