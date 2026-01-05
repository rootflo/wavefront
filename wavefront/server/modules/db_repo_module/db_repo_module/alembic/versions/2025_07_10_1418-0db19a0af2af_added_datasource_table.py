"""Added datasource table

Revision ID: 0db19a0af2af
Revises: 827b9d399023
Create Date: 2025-07-04 14:18:48.271013

"""

import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0db19a0af2af'
down_revision: Union[str, None] = '827b9d399023'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'datasource',
        sa.Column('id', sa.UUID(), nullable=False, default=uuid.uuid4),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('type', sa.String(length=64), nullable=False),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.Column(
            'updated_at',
            sa.DateTime(),
            nullable=False,
            default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_datasource_id'), 'datasource', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_datasource_id'), table_name='datasource')
    op.drop_table('datasource')
