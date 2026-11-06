"""add_app_migrations_table

Adds `app_migrations`, the ledger of one-time app migrations
(floware/app_migrations) this deployment has run.

Revision ID: e2a6c8d4f1b9
Revises: b3c8f1d6a2e4
Create Date: 2026-11-03 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e2a6c8d4f1b9'
down_revision: Union[str, None] = 'b3c8f1d6a2e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'app_migrations',
        sa.Column('revision', sa.String(length=64), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('summary', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('applied_by', sa.String(length=32), nullable=False),
        sa.Column('app_version', sa.String(length=64), nullable=True),
        sa.Column(
            'started_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
        ),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('revision'),
    )


def downgrade() -> None:
    op.drop_table('app_migrations')
