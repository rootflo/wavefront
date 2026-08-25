"""create datasource_audit_logs table

Revision ID: d4f1a7c3e2b8
Revises: 314534601d35
Create Date: 2026-08-20 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd4f1a7c3e2b8'
down_revision: Union[str, None] = '314534601d35'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'datasource_audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('batch_id', postgresql.UUID(as_uuid=True), nullable=False),
        # Intentionally no ForeignKeyConstraint to datasource.id: that row is
        # hard-deleted, and the audit trail has to outlive it.
        sa.Column('datasource_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            'datasource_type',
            sa.String(length=32),
            nullable=False,
            comment='possible values: postgres, gcp_bigquery, aws_redshift, mssql',
        ),
        sa.Column('table_name', sa.String(length=512), nullable=False),
        sa.Column(
            'operation',
            sa.String(length=16),
            nullable=False,
            comment='possible values: insert, update, delete',
        ),
        sa.Column('filter', sa.String(length=512), nullable=True),
        sa.Column(
            'filter_params', postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column('changes', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('meta', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('rows_affected', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('user_id', sa.String(length=255), nullable=False),
        sa.Column('role_id', sa.String(length=255), nullable=False),
        sa.Column('request_id', sa.String(length=64), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_datasource_audit_logs_id'), 'datasource_audit_logs', ['id']
    )
    op.create_index(
        op.f('ix_datasource_audit_logs_batch_id'), 'datasource_audit_logs', ['batch_id']
    )
    # (selective_col, created_at) so one scan serves both the equality filter
    # and the ORDER BY created_at DESC every listing uses.
    op.create_index(
        'ix_datasource_audit_logs_datasource_created',
        'datasource_audit_logs',
        ['datasource_id', 'created_at'],
    )
    op.create_index(
        'ix_datasource_audit_logs_table_created',
        'datasource_audit_logs',
        ['table_name', 'created_at'],
    )
    op.create_index(
        'ix_datasource_audit_logs_user_created',
        'datasource_audit_logs',
        ['user_id', 'created_at'],
    )
    # Plain btree: exact match and left-anchored prefix only. Substring search
    # would need a GIN trigram index (pg_trgm), deferred until it is a real
    # access pattern.
    op.create_index(
        'ix_datasource_audit_logs_filter', 'datasource_audit_logs', ['filter']
    )


def downgrade() -> None:
    op.drop_index('ix_datasource_audit_logs_filter', table_name='datasource_audit_logs')
    op.drop_index(
        'ix_datasource_audit_logs_user_created', table_name='datasource_audit_logs'
    )
    op.drop_index(
        'ix_datasource_audit_logs_table_created', table_name='datasource_audit_logs'
    )
    op.drop_index(
        'ix_datasource_audit_logs_datasource_created',
        table_name='datasource_audit_logs',
    )
    op.drop_index(
        op.f('ix_datasource_audit_logs_batch_id'), table_name='datasource_audit_logs'
    )
    op.drop_index(
        op.f('ix_datasource_audit_logs_id'), table_name='datasource_audit_logs'
    )
    op.drop_table('datasource_audit_logs')
