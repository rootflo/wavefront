"""renaming column in leads table

Revision ID: d77dca43b31d
Revises: 053823285206
Create Date: 2025-05-02 12:39:41.115042

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd77dca43b31d'
down_revision: Union[str, None] = '053823285206'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('leads', 'start', new_column_name='start_date')
    op.alter_column('leads', 'end', new_column_name='end_date')
    op.execute(
        "UPDATE notification SET type = 'warning' WHERE type = 'product_issues';"
    )


def downgrade() -> None:
    op.alter_column('leads', 'start_date', new_column_name='start')
    op.alter_column('leads', 'end_date', new_column_name='end')
    op.execute(
        "UPDATE notification SET type = 'product_issues' WHERE type = 'warning';"
    )
