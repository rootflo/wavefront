"""create user group tables

Revision ID: a3e7c91d4b26
Revises: c4d8b2e6a917
Create Date: 2026-09-14 13:00:00.000000

Groups bundle roles so they can be handed to several users at once. A user's
effective roles become the union of their direct `user_role` rows and the roles
of every group they belong to.

Both join tables are optional links: a group with no rows in `user_group_role`
grants nothing, and one with no rows in `user_group_member` has no members.
Neither is an error, so no minimum is enforced here.

Additive only -- no existing table is touched.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a3e7c91d4b26'
down_revision: Union[str, None] = 'c4d8b2e6a917'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'user_group',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_user_group_name'),
    )
    op.create_index(op.f('ix_user_group_id'), 'user_group', ['id'], unique=False)

    # group_id/user_id mirror the parent primary keys: user.id is a uuid column
    # while role.id is a string, matching how user_role is already typed.
    op.create_table(
        'user_group_member',
        sa.Column('group_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(['group_id'], ['user_group.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('group_id', 'user_id'),
    )
    op.create_index(
        op.f('ix_user_group_member_user_id'),
        'user_group_member',
        ['user_id'],
        unique=False,
    )

    op.create_table(
        'user_group_role',
        sa.Column('group_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role_id', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['group_id'], ['user_group.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['role_id'], ['role.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('group_id', 'role_id'),
    )
    op.create_index(
        op.f('ix_user_group_role_role_id'),
        'user_group_role',
        ['role_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_user_group_role_role_id'), table_name='user_group_role')
    op.drop_table('user_group_role')
    op.drop_index(op.f('ix_user_group_member_user_id'), table_name='user_group_member')
    op.drop_table('user_group_member')
    op.drop_index(op.f('ix_user_group_id'), table_name='user_group')
    op.drop_table('user_group')
