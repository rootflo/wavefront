"""create default app

Revision ID: a1b2c3d4e5f6
Revises: 85a63aed0f81
Create Date: 2025-12-13 14:00:00.000000

"""

import os
import uuid
from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '85a63aed0f81'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Get environment variables for default app
    default_app_name = os.getenv('DEFAULT_APP_NAME')
    default_app_public_url = os.getenv('DEFAULT_APP_PUBLIC_URL')
    default_app_private_url = os.getenv('DEFAULT_APP_PRIVATE_URL')

    # Only create default app if all required env variables are set
    if default_app_name and default_app_public_url and default_app_private_url:
        # Check if a default app already exists with the same name
        conn = op.get_bind()
        # Insert default app using SQLAlchemy Table reflection for better type safety
        app_id = uuid.uuid4()
        app_table = sa.Table('app', sa.MetaData(), autoload_with=conn)
        insert_stmt = app_table.insert().values(
            id=app_id,
            app_name=default_app_name,
            public_url=default_app_public_url,
            private_url=default_app_private_url,
            deleted=False,
            status='success',
            config='{}',
            deployment_type='manual',
            type='custom',
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        conn.execute(insert_stmt)


def downgrade() -> None:
    # Get environment variables for default app
    default_app_name = os.getenv('DEFAULT_APP_NAME')

    # Only remove default app if env variable is set
    if default_app_name:
        conn = op.get_bind()
        conn.execute(
            sa.text('DELETE FROM app WHERE app_name = :app_name'),
            {'app_name': default_app_name},
        )
