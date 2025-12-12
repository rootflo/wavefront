"""create leads table

Revision ID: 053823285206
Revises: a0dfba41ef64
Create Date: 2025-04-29 13:45:07.797358

"""

from typing import Sequence, Union
import uuid

from alembic import op
from sqlalchemy import UUID
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '053823285206'
down_revision: Union[str, None] = 'a0dfba41ef64'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'leads',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('product_category', sa.String, nullable=True),
        sa.Column('conversation_id', sa.String, nullable=True),
        sa.Column('customer_id', sa.String, nullable=True),
        sa.Column('agent_id', sa.String, nullable=True),
        sa.Column('branch', sa.String, nullable=True),
        sa.Column('region', sa.String, nullable=True),
        sa.Column('start', sa.Date(), nullable=False),
        sa.Column('end', sa.Date(), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True
        ),
        sa.Column(
            'updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True
        ),
        # adding an column for leads table
        sa.Column('product_name', sa.String, nullable=False),
        sa.Column('type', sa.String, nullable=False),
    )


def downgrade() -> None:
    op.drop_table('leads')
