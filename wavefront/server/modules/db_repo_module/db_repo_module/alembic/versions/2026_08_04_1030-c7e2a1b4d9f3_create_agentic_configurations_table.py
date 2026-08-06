"""create agentic_configurations table

Revision ID: c7e2a1b4d9f3
Revises: 1d6a0d5cfd6f
Create Date: 2026-08-04 10:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c7e2a1b4d9f3'
down_revision: Union[str, None] = '1d6a0d5cfd6f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'agentic_configurations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('namespace', sa.String(length=255), nullable=False),
        sa.Column('key', sa.String(length=255), nullable=False),
        sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            'updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(['namespace'], ['namespaces.name']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'namespace', 'key', name='uq_agentic_configurations_namespace_key'
        ),
    )
    op.create_index(
        op.f('ix_agentic_configurations_id'), 'agentic_configurations', ['id']
    )
    op.create_index(
        op.f('ix_agentic_configurations_namespace'),
        'agentic_configurations',
        ['namespace'],
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_agentic_configurations_namespace'),
        table_name='agentic_configurations',
    )
    op.drop_index(
        op.f('ix_agentic_configurations_id'), table_name='agentic_configurations'
    )
    op.drop_table('agentic_configurations')
