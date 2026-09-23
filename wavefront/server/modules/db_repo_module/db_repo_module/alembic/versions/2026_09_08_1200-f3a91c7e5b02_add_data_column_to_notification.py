"""add data jsonb column and ordering index to notification

The notification table was effectively write-free: nothing in the codebase
inserted into it. Datasource row mutations now push a row per mutating request,
which changes two things.

`data` carries the structured payload behind the row -- for a datasource change,
the per-table `changes` documents already built for datasource_audit_logs.
`title` remains a denormalized summary; `data` is what a consumer renders from.
Nullable, because rows predating this column have none and a producer may notify
without a payload.

The index exists because the listing's ORDER BY can no longer be a sort of the
whole table. It is (created_at DESC, id DESC) rather than created_at alone: the
listing pages with LIMIT/OFFSET, created_at is not unique under concurrent
inserts, and an unstable sort makes offset pagination skip and repeat rows.

Revision ID: f3a91c7e5b02
Revises: 7d4ca468f0b0
Create Date: 2026-09-08 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f3a91c7e5b02'
down_revision: Union[str, None] = '7d4ca468f0b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'notification',
        sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index(
        'ix_notification_created_at',
        'notification',
        [sa.text('created_at DESC'), sa.text('id DESC')],
    )


def downgrade() -> None:
    op.drop_index('ix_notification_created_at', table_name='notification')
    op.drop_column('notification', 'data')
