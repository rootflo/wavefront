"""drop_actionable_alert_insight_leads_table

Revision ID: 10e09e25efa0
Revises: ca83b60258d6
Create Date: 2025-12-01 16:19:58.228914

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '10e09e25efa0'
down_revision: Union[str, None] = 'ca83b60258d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the three tables
    op.drop_table('actionable_alerts', if_exists=True)
    op.drop_table('actionable_insight_queries', if_exists=True)
    op.drop_table('leads', if_exists=True)


def downgrade() -> None:
    pass
