"""add seed user

Revision ID: 521ae4960bcf
Revises: e3a2fa91cda2
Create Date: 2025-08-18 15:54:31.167317

"""

from alembic import op
import sqlalchemy as sa
import uuid
import os

from floconsole.utils.password_utils import hash_password


# revision identifiers, used by Alembic.
revision = '521ae4960bcf'
down_revision = 'e3a2fa91cda2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Get user details from environment variables
    email = os.getenv('CONSOLE_EMAIL')
    password = os.getenv('CONSOLE_PASSWORD')
    f_name = os.getenv('CONSOLE_FIRST_NAME')
    l_name = os.getenv('CONSOLE_LAST_NAME')

    # Skip if environment variables are not set
    if not all([email, password, f_name, l_name]):
        print(
            'Skipping seed user creation - missing environment variables (CONSOLE_EMAIL, CONSOLE_PASSWORD, CONSOLE_FIRST_NAME, CONSOLE_LAST_NAME)'
        )
        return

    assert email is not None
    assert password is not None
    assert f_name is not None
    assert l_name is not None

    hashed_password = hash_password(password)

    # Insert seed user using connection
    conn = op.get_bind()
    conn.execute(
        sa.text("""
            INSERT INTO "user" (id, email, password, first_name, last_name, deleted, failed_attempts, locked_until, last_failed_attempt)
            VALUES (:id, :email, :password, :first_name, :last_name, :deleted, :failed_attempts, :locked_until, :last_failed_attempt)
        """),
        {
            'id': uuid.uuid4(),
            'email': email,
            'password': hashed_password,  # Should be hashed before passing to migration
            'first_name': f_name,
            'last_name': l_name,
            'deleted': False,
            'failed_attempts': 0,
            'locked_until': None,
            'last_failed_attempt': None,
        },
    )


def downgrade() -> None:
    # Get email from environment variable
    email = os.getenv('CONSOLE_EMAIL')
    if email:
        conn = op.get_bind()
        conn.execute(
            sa.text('DELETE FROM "user" WHERE email = :email'), {'email': email}
        )
