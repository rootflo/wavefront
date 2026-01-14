"""add role to user

Revision ID: 0644a81ee4e1
Revises: a1b2c3d4e5f6
Create Date: 2026-01-06 16:44:06.062916

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0644a81ee4e1'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add role column with default
    op.add_column(
        'user',
        sa.Column('role', sa.String(), nullable=False, server_default='app_admin'),
    )

    # Set all existing users to 'owner'
    conn = op.get_bind()
    conn.execute(sa.text('UPDATE "user" SET role = \'owner\' WHERE deleted = false'))

    # Remove server_default (app handles default)
    op.alter_column('user', 'role', server_default=None)

    # Add index for role queries
    op.create_index(op.f('ix_user_role'), 'user', ['role'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_user_role'), table_name='user')
    op.drop_column('user', 'role')
