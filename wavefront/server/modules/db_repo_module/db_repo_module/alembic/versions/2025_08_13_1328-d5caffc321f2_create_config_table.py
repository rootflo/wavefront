"""create config table

Revision ID: d5caffc321f2
Revises: 1ef7d577ea53
Create Date: 2025-08-18 12:28:31.653508

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd5caffc321f2'
down_revision: Union[str, None] = '1ef7d577ea53'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'config',
        sa.Column('key', sa.String(255), primary_key=True),
        sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False, default=sa.func.now()),
        sa.Column(
            'updated_at',
            sa.DateTime,
            nullable=False,
            default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table('config')
