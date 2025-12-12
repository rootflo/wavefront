"""remove_app_key_and_app_secret

Revision ID: 85a63aed0f81
Revises: 480783ba0ace
Create Date: 2025-12-09 13:28:06.158846

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '85a63aed0f81'
down_revision = '480783ba0ace'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Remove app_key and app_secret columns, rename app_url to public_url, and add private_url"""
    # Step 1: Remove app_key and app_secret columns
    op.drop_column('app', 'app_secret')
    op.drop_column('app', 'app_key')

    # Step 2: Add private_url as nullable (temporary)
    op.add_column('app', sa.Column('private_url', sa.String(), nullable=True))

    # Step 3: Populate private_url with existing app_url values
    op.execute('UPDATE app SET private_url = app_url')

    # Step 4: Rename app_url to public_url
    op.alter_column('app', 'app_url', new_column_name='public_url')

    # Step 5: Make private_url non-nullable
    op.alter_column('app', 'private_url', nullable=False)


def downgrade() -> None:
    """Restore app_key and app_secret columns, rename public_url back to app_url, and remove private_url"""
    # Step 1: Rename public_url back to app_url
    op.alter_column('app', 'public_url', new_column_name='app_url')

    # Step 2: Drop private_url column
    op.drop_column('app', 'private_url')

    # Step 3: Restore app_key and app_secret columns as nullable
    op.add_column('app', sa.Column('app_key', sa.String(), nullable=True))
    op.add_column('app', sa.Column('app_secret', sa.String(), nullable=True))
