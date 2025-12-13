"""for actionable insights

Revision ID: c7800bd1d9c3
Revises: 01a4c5202566
Create Date: 2025-02-10 11:33:33.664976

"""

from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.mutable import MutableDict

# revision identifiers, used by Alembic.
revision: str = 'c7800bd1d9c3'
down_revision: Union[str, None] = '01a4c5202566'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'actionable_alerts',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('signal_id', sa.String, nullable=False),
        sa.Column('title', sa.String, nullable=True),
        sa.Column('description', sa.String, nullable=True),
        sa.Column('signal_type', sa.String, nullable=False),
        sa.Column('alerts', MutableDict.as_mutable(JSONB), nullable=True),
        sa.Column('data', MutableDict.as_mutable(JSONB), nullable=True),
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
    )


def downgrade() -> None:
    op.drop_table('actionable_alerts')
