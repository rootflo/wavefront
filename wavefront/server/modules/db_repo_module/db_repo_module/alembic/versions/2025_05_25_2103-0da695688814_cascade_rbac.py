"""cascade-rbac

Revision ID: 0da695688814
Revises: ba1f66ca0228
Create Date: 2025-05-25 21:03:49.706665

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0da695688814'
down_revision: Union[str, None] = 'ba1f66ca0228'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Clean up orphaned records
    op.execute("""
        DELETE FROM user_role
        WHERE user_id NOT IN (SELECT id FROM "user")
        OR role_id NOT IN (SELECT id FROM role)
    """)

    op.execute("""
        DELETE FROM role_resource
        WHERE role_id NOT IN (SELECT id FROM role)
        OR resource_id NOT IN (SELECT id FROM resource)
    """)

    # Drop existing foreign key constraints
    op.drop_constraint('user_role_user_id_fkey', 'user_role', type_='foreignkey')
    op.drop_constraint(
        'role_resource_role_id_fkey', 'role_resource', type_='foreignkey'
    )

    # Add new foreign key constraints with CASCADE
    op.create_foreign_key(
        'user_role_user_id_fkey',
        'user_role',
        'user',
        ['user_id'],
        ['id'],
        ondelete='CASCADE',
    )
    op.create_foreign_key(
        'role_resource_role_id_fkey',
        'role_resource',
        'role',
        ['role_id'],
        ['id'],
        ondelete='CASCADE',
    )


def downgrade() -> None:
    # Drop CASCADE foreign key constraints
    op.drop_constraint('user_role_user_id_fkey', 'user_role', type_='foreignkey')
    op.drop_constraint(
        'role_resource_role_id_fkey', 'role_resource', type_='foreignkey'
    )

    # Recreate original foreign key constraints without CASCADE
    op.create_foreign_key(
        'user_role_user_id_fkey', 'user_role', 'user', ['user_id'], ['id']
    )
    op.create_foreign_key(
        'role_resource_role_id_fkey', 'role_resource', 'role', ['role_id'], ['id']
    )
