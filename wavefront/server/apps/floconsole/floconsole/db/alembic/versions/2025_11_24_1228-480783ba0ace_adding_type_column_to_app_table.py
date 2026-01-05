"""Adding type column to app table

Revision ID: 480783ba0ace
Revises: 49e97617960c
Create Date: 2025-11-24 12:28:36.127318

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '480783ba0ace'
down_revision = '49e97617960c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'app',
        sa.Column(
            'deployment_type',
            sa.String(length=255),
            nullable=False,
            server_default='manual',
        ),
    )
    op.add_column(
        'app',
        sa.Column(
            'type', sa.String(length=255), nullable=False, server_default='custom'
        ),
    )


def downgrade() -> None:
    op.drop_column('app', 'deployment_type')
    op.drop_column('app', 'type')
