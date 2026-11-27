"""add run parameters and retry lineage to async_agentic_executions

A failed execution could only be re-run by resubmitting the whole request. To
retry it from the row, the row must hold everything the worker payload did:
`inputs` and `variables` already are, but `version`, `output_json_enabled` and
`llm_inference_config_id` only ever reached the Celery payload. All three are
nullable, because older rows have none.

Lineage: `retry_of_execution_id` is the execution this one retried. It is
unique, so an execution can be retried at most once even under concurrent
requests, and a chain stays linear. `attempt` is the row's position in its chain, starting at 1, and is what the
configured attempt cap is checked against.

Revision ID: d7f2a9c4e1b3
Revises: e2a6c8d4f1b9
Create Date: 2026-11-20 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd7f2a9c4e1b3'
down_revision: Union[str, None] = 'e2a6c8d4f1b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'async_agentic_executions'


def upgrade() -> None:
    op.add_column(TABLE, sa.Column('version', sa.Integer(), nullable=True))
    op.add_column(TABLE, sa.Column('output_json_enabled', sa.Boolean(), nullable=True))
    op.add_column(
        TABLE,
        sa.Column(
            'llm_inference_config_id', postgresql.UUID(as_uuid=True), nullable=True
        ),
    )
    op.add_column(
        TABLE,
        sa.Column(
            'retry_of_execution_id', postgresql.UUID(as_uuid=True), nullable=True
        ),
    )
    op.add_column(
        TABLE,
        sa.Column('attempt', sa.Integer(), nullable=False, server_default='1'),
    )
    op.create_foreign_key(
        'async_agentic_executions_retry_of_execution_id_fkey',
        TABLE,
        TABLE,
        ['retry_of_execution_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.create_unique_constraint(
        'async_agentic_executions_retry_of_execution_id_key',
        TABLE,
        ['retry_of_execution_id'],
    )


def downgrade() -> None:
    op.drop_constraint(
        'async_agentic_executions_retry_of_execution_id_key', TABLE, type_='unique'
    )
    op.drop_constraint(
        'async_agentic_executions_retry_of_execution_id_fkey',
        TABLE,
        type_='foreignkey',
    )
    op.drop_column(TABLE, 'attempt')
    op.drop_column(TABLE, 'retry_of_execution_id')
    op.drop_column(TABLE, 'llm_inference_config_id')
    op.drop_column(TABLE, 'output_json_enabled')
    op.drop_column(TABLE, 'version')
