"""initializing the role table

Revision ID: 17c4ba1a32fe
Revises: f6b7ce8e5b03
Create Date: 2024-12-04 13:27:39.664369

"""

import os
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision: str = '17c4ba1a32fe'
down_revision: Union[str, None] = 'f6b7ce8e5b03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)

    try:
        if 'role' in inspector.get_table_names():
            admin_id = uuid.uuid4()
            conn.execute(
                sa.text(
                    """
                    INSERT INTO role (id, name, description)
                    VALUES (:id, :name, :description)
                """
                ),
                [
                    {
                        'id': admin_id,
                        'name': 'admin',
                        'description': 'Admin role with full permissions',
                    },
                    {
                        'id': uuid.uuid4(),
                        'name': 'read',
                        'description': 'read role with limited permission',
                    },
                    {
                        'id': uuid.uuid4(),
                        'name': 'read_write',
                        'description': 'read and write role with moderate permission',
                    },
                ],
            )
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
                    'team_id': 'team1',
                    'role_id': admin_id,
                },
            )

    except Exception as e:
        raise e


def downgrade() -> None:
    op.execute(
        sa.text(
            """
        DELETE FROM "user"
        WHERE email = 'sanosh@example.com';
    """
        )
    )
    op.execute(
        sa.text(
            """
        DELETE FROM "role"
        WHERE name='admin';
    """
        )
    )
