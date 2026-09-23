"""add variables jsonb column to async_agentic_executions

An async execution row recorded `inputs` and `input_files` but nothing about the
`variables` the run was parameterised with, even though variables are the only
channel that reaches a node's prompt. That made a completed execution
impossible to audit or reproduce from the row alone.

The column holds the raw variables the caller sent, not the dict handed to the
worker: `with_execution_variables()` injects an internal `_wf_execution_id` key
into the Celery payload, and that value is already this row's `id`.

Nullable, because rows predating this column have none and a caller may run
without variables at all.

The GIN index makes the column queryable by content -- "every execution run for
customer_id X" -- which a btree on a jsonb column cannot serve. It uses the
default jsonb_ops rather than jsonb_path_ops: jsonb_path_ops is smaller and
faster but only supports containment (@>), while jsonb_ops also covers key
existence (?, ?&, ?|). Callers' variable shapes are arbitrary and no query
filters on this column yet, so the more permissive operator class is the right
hedge; narrow it to jsonb_path_ops if containment turns out to be the only
access pattern.

Revision ID: c4d8b2e6a917
Revises: f3a91c7e5b02
Create Date: 2026-09-10 11:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c4d8b2e6a917'
down_revision: Union[str, None] = 'f3a91c7e5b02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'async_agentic_executions',
        sa.Column('variables', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index(
        'ix_async_agentic_executions_variables_gin',
        'async_agentic_executions',
        ['variables'],
        postgresql_using='gin',
    )


def downgrade() -> None:
    op.drop_index(
        'ix_async_agentic_executions_variables_gin',
        table_name='async_agentic_executions',
    )
    op.drop_column('async_agentic_executions', 'variables')
