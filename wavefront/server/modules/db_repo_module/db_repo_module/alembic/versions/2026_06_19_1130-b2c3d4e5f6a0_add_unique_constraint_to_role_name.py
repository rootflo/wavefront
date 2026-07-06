"""add unique constraint to role name

Revision ID: b2c3d4e5f6a0
Revises: a1b2c3d4e5f8
Create Date: 2026-06-19 11:30:00.000000

Admin (and every other role) is identified across the codebase by name
(e.g. check_is_admin -> role.name == ADMIN_ROLE_NAME). Enforce uniqueness so
a given role name maps to exactly one role id.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a0'
down_revision: Union[str, None] = 'a1b2c3d4e5f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    duplicates = conn.execute(
        sa.text(
            'SELECT name, COUNT(*) AS count FROM role '
            'GROUP BY name HAVING COUNT(*) > 1'
        )
    ).fetchall()
    if duplicates:
        details = ', '.join(f'{row.name} (x{row.count})' for row in duplicates)
        raise RuntimeError(
            'Cannot add unique constraint on role.name; duplicate role names '
            f'exist and must be merged manually first: {details}'
        )

    op.create_unique_constraint('uq_role_name', 'role', ['name'])


def downgrade() -> None:
    op.drop_constraint('uq_role_name', 'role', type_='unique')
