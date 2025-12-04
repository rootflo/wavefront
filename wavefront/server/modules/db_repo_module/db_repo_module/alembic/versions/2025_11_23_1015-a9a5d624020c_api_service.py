"""api_service

Revision ID: a9a5d624020c
Revises: af9dfcda24fb
Create Date: 2025-11-23 10:15:22.245337

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a9a5d624020c'
down_revision: Union[str, None] = 'af9dfcda24fb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'api_services',
        sa.Column('id', sa.String(length=255), nullable=False),
        sa.Column('service_def_path', sa.String(length=255), nullable=False),
        sa.Column(
            'is_active',
            sa.Boolean(),
            nullable=False,
            default=True,
            server_default=sa.text('true'),
        ),
        sa.Column(
            'created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')
        ),
        sa.Column(
            'updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')
        ),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('api_services')
