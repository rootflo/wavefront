"""Update apps table

Revision ID: 49e97617960c
Revises: ac10dc573599
Create Date: 2025-10-14 14:23:30.306132

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '49e97617960c'
down_revision = 'ac10dc573599'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'app',
        sa.Column('status', sa.String(), nullable=False, server_default='success'),
    )
    op.add_column(
        'app', sa.Column('config', sa.JSON(), nullable=False, server_default='{}')
    )

    op.alter_column('app', 'app_secret', nullable=True)
    op.alter_column('app', 'app_key', nullable=True)

    op.alter_column('app', 'status', server_default=None)
    op.alter_column('app', 'config', server_default=None)


def downgrade() -> None:
    op.alter_column('app', 'app_secret', nullable=False)
    op.alter_column('app', 'app_key', nullable=False)

    op.drop_column('app', 'config')
    op.drop_column('app', 'status')
