"""Create authenticators table

Revision ID: a1b2c3d4e5f7
Revises: 0db19a0af2af
Create Date: 2025-07-14 14:00:00.000000

"""

import json
import uuid
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f7'
down_revision: Union[str, None] = '0db19a0af2af'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create authenticator table
    op.create_table(
        'authenticator',
        sa.Column(
            'auth_id',
            postgresql.UUID(as_uuid=True),
            nullable=False,
            primary_key=True,
            default=sa.text('gen_random_uuid()'),
        ),
        sa.Column('auth_name', sa.String(length=64), nullable=False, unique=True),
        sa.Column('auth_type', sa.String(), nullable=False),
        sa.Column('auth_desc', sa.String(), nullable=True),
        sa.Column('config', postgresql.JSONB(), nullable=False),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, default=True),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, default=False),
        sa.Column(
            'created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint('auth_id'),
        sa.UniqueConstraint('auth_name'),
        sa.CheckConstraint("auth_name !~ '\\s'", name='auth_name_no_spaces'),
    )

    # Get database connection
    conn = op.get_bind()

    # Default email_password authenticator configuration
    default_config = {
        'password_policy': {
            'min_length': 8,
            'require_uppercase': True,
            'require_lowercase': True,
            'require_numbers': True,
            'require_special_chars': False,
            'max_attempts': 5,
            'lockout_duration': 900,
        },
        'two_factor_enabled': False,
        'password_reset_enabled': True,
        'session_timeout': 3600,
        'rate_limit_enabled': True,
    }

    # Insert default email_password authenticator using parameterized statement
    conn.execute(
        sa.text("""
            INSERT INTO authenticator (auth_id, auth_name, auth_type, auth_desc, config, is_enabled, is_deleted)
            VALUES (:auth_id, :auth_name, :auth_type, :auth_desc, :config, :is_enabled, :is_deleted)
        """),
        {
            'auth_id': uuid.uuid4(),
            'auth_name': 'email_password',
            'auth_type': 'email_password',
            'auth_desc': 'Traditional email and password authentication',
            'config': json.dumps(default_config),
            'is_enabled': True,
            'is_deleted': False,
        },
    )


def downgrade() -> None:
    # Drop authenticator table
    op.drop_table('authenticator')
