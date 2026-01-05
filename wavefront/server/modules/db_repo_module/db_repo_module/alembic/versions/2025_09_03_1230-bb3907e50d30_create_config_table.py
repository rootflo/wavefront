"""create config table

Revision ID: bb3907e50d30
Revises: 23db0be3a87a
Create Date: 2025-09-03 12:30:17.664871

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bb3907e50d30'
down_revision: Union[str, None] = '23db0be3a87a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'dynamic_query_yaml',
        sa.Column('name', sa.String(255), primary_key=True),
        sa.Column('datasource_id', sa.UUID(), nullable=True),  # Changed to UUID
        sa.Column('file_path', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False, default=sa.func.now()),
        sa.Column(
            'updated_at',
            sa.DateTime,
            nullable=False,
            default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ['datasource_id'], ['datasource.id'], ondelete='CASCADE'
        ),
    )


def downgrade() -> None:
    op.drop_table('dynamic_query_yaml')
