"""truncating role table

Revision ID: 756caddfb44b
Revises: 17c4ba1a32fe
Create Date: 2024-12-09 10:30:19.749358

"""

import os
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '756caddfb44b'
down_revision: Union[str, None] = '17c4ba1a32fe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    try:
        conn.execute(sa.text("""TRUNCATE TABLE "user" """))
        result = conn.execute(sa.text("SELECT id FROM role WHERE name = 'admin'"))
        admin_id = result.scalar()
        if not admin_id:
            raise ValueError('Admin role not found in the role table.')
        email = os.getenv('EMAIL')
        password = os.getenv('PASSWORD')
        f_name = os.getenv('FIRST_NAME')
        l_name = os.getenv('LAST_NAME')
        conn.execute(
            sa.text(
                """
                    INSERT INTO "user" (id, email, password, first_name, last_name, team_id, role_id)
                    VALUES (:id, :email, :password, :first_name, :last_name, :team_id, :role_id)
                """
            ),
            {
                'id': uuid.uuid4(),
                'email': email,
                'password': password,
                'first_name': f_name,
                'last_name': l_name,
                'team_id': 'team-1',
                'role_id': admin_id,
            },
        )
    except Exception as e:
        raise e


def downgrade() -> None:
    pass
