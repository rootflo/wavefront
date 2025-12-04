"""Remove all wrongly generated alerts

Revision ID: f9c4c1c48d46
Revises: 76ba9543af92
Create Date: 2025-02-22 12:36:16.510535

"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy.orm import Session
from sqlalchemy.sql import text

# revision identifiers, used by Alembic.
revision: str = 'f9c4c1c48d46'
down_revision: Union[str, None] = '76ba9543af92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)

    latest_20_rows = session.execute(
        text('SELECT id FROM actionable_alerts ORDER BY created_at DESC LIMIT 20')
    ).fetchall()

    if latest_20_rows:
        # Extract the 20 IDs to keep
        ids_to_keep = tuple(row[0] for row in latest_20_rows)

        # Delete all rows except these 20
        session.execute(
            text('DELETE FROM actionable_alerts WHERE id NOT IN :ids'),
            {'ids': ids_to_keep},
        )
        session.commit()


def downgrade() -> None:
    pass
