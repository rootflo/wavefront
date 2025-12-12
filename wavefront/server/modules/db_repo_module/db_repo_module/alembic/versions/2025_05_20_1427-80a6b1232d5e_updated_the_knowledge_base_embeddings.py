"""Updated the knowledge_base_embeddings

Revision ID: 80a6b1232d5e
Revises: 497a13558d60
Create Date: 2025-05-20 14:27:52.192885

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '80a6b1232d5e'
down_revision: Union[str, None] = '497a13558d60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('knowledge_base_embeddings', sa.Column('token', postgresql.TSVECTOR))


def downgrade() -> None:
    op.drop_column('knowledge_base_embeddings', 'token')
