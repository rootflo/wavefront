"""hash_existing_passwords

Revision ID: 01a4c5202566
Revises: 756caddfb44b
Create Date: 2024-12-17 14:12:08.397545

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from user_management_module.utils.password_utils import hash_password

# revision identifiers, used by Alembic.
revision: str = '01a4c5202566'
down_revision: Union[str, None] = '756caddfb44b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    result = conn.execute(
        sa.text('SELECT id, password FROM "user" WHERE password IS NOT NULL')
    )
    users = result.fetchall()

    for user in users:
        user_id, plain_password = user

        if plain_password.startswith('$2b$'):
            continue

        hashed_password = hash_password(plain_password)

        conn.execute(
            sa.text('UPDATE "user" SET password = :password WHERE id = :id'),
            {'password': hashed_password, 'id': user_id},
        )


def downgrade() -> None:
    pass
