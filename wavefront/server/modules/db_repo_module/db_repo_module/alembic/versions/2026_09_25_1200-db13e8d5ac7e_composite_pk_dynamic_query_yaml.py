"""composite primary key for dynamic_query_yaml

Revision ID: db13e8d5ac7e
Revises: f8c2a91e4b07
Create Date: 2026-09-25 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'db13e8d5ac7e'
down_revision: Union[str, None] = 'f8c2a91e4b07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # datasource_id must be non-null to take part in the primary key.
    op.alter_column(
        'dynamic_query_yaml',
        'datasource_id',
        existing_type=sa.UUID(),
        nullable=False,
    )
    op.drop_constraint('dynamic_query_yaml_pkey', 'dynamic_query_yaml', type_='primary')
    op.create_primary_key(
        'dynamic_query_yaml_pkey',
        'dynamic_query_yaml',
        ['name', 'datasource_id'],
    )


def downgrade() -> None:
    op.drop_constraint('dynamic_query_yaml_pkey', 'dynamic_query_yaml', type_='primary')
    op.create_primary_key(
        'dynamic_query_yaml_pkey',
        'dynamic_query_yaml',
        ['name'],
    )
    op.alter_column(
        'dynamic_query_yaml',
        'datasource_id',
        existing_type=sa.UUID(),
        nullable=True,
    )
