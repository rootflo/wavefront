"""Adding Cacade Delete

Revision ID: 36703628c7a6
Revises: 9b10292a95eb
Create Date: 2025-03-31 17:15:08.654501

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '36703628c7a6'
down_revision: Union[str, None] = '9b10292a95eb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop existing foreign key constraints
    op.drop_constraint(
        'role_resource_resource_id_fkey', 'role_resource', type_='foreignkey'
    )
    op.drop_constraint(
        'role_resource_role_id_fkey', 'role_resource', type_='foreignkey'
    )
    op.drop_constraint('user_role_role_id_fkey', 'user_role', type_='foreignkey')
    op.drop_constraint('user_role_user_id_fkey', 'user_role', type_='foreignkey')

    # Create new foreign key constraints with CASCADE delete
    op.create_foreign_key(
        'role_resource_resource_id_fkey',
        'role_resource',
        'resource',
        ['resource_id'],
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
    op.create_foreign_key(
        'user_role_role_id_fkey',
        'user_role',
        'role',
        ['role_id'],
        ['id'],
        ondelete='CASCADE',
    )
    op.create_foreign_key(
        'user_role_user_id_fkey',
        'user_role',
        'user',
        ['user_id'],
        ['id'],
        ondelete='CASCADE',
    )


def downgrade() -> None:
    # Drop CASCADE foreign key constraints
    op.drop_constraint(
        'role_resource_resource_id_fkey', 'role_resource', type_='foreignkey'
    )
    op.drop_constraint(
        'role_resource_role_id_fkey', 'role_resource', type_='foreignkey'
    )
    op.drop_constraint('user_role_role_id_fkey', 'user_role', type_='foreignkey')
    op.drop_constraint('user_role_user_id_fkey', 'user_role', type_='foreignkey')

    # Recreate original foreign key constraints without CASCADE
    op.create_foreign_key(
        'role_resource_resource_id_fkey',
        'role_resource',
        'resource',
        ['resource_id'],
        ['id'],
    )
    op.create_foreign_key(
        'role_resource_role_id_fkey', 'role_resource', 'role', ['role_id'], ['id']
    )
    op.create_foreign_key(
        'user_role_role_id_fkey', 'user_role', 'role', ['role_id'], ['id']
    )
    op.create_foreign_key(
        'user_role_user_id_fkey', 'user_role', 'user', ['user_id'], ['id']
    )
