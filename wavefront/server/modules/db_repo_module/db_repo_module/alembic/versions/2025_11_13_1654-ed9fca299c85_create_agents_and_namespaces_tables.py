"""create_agents_namespaces_and_workflows_tables

Revision ID: ed9fca299c85
Revises: 584f653169fd
Create Date: 2025-11-13 16:54:05.535954

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'ed9fca299c85'
down_revision: Union[str, None] = '584f653169fd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create namespaces table first (parent)
    op.create_table(
        'namespaces',
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')
        ),
        sa.Column(
            'updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')
        ),
        sa.PrimaryKeyConstraint('name'),
    )
    op.create_index(op.f('ix_namespaces_name'), 'namespaces', ['name'], unique=True)

    # Insert default namespace
    op.execute("INSERT INTO namespaces (name) VALUES ('default')")

    # Create agents table (child with FK to namespaces)
    op.create_table(
        'agents',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('namespace', sa.String(length=255), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')
        ),
        sa.Column(
            'updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')
        ),
        sa.ForeignKeyConstraint(['namespace'], ['namespaces.name']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', 'namespace', name='uq_agents_name_namespace'),
    )
    op.create_index(op.f('ix_agents_id'), 'agents', ['id'], unique=False)
    op.create_index(op.f('ix_agents_namespace'), 'agents', ['namespace'], unique=False)

    # Create workflows table (child with FK to namespaces)
    op.create_table(
        'workflows',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('namespace', sa.String(length=255), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')
        ),
        sa.Column(
            'updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')
        ),
        sa.ForeignKeyConstraint(['namespace'], ['namespaces.name']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', 'namespace', name='uq_workflows_name_namespace'),
    )
    op.create_index(op.f('ix_workflows_id'), 'workflows', ['id'], unique=False)
    op.create_index(
        op.f('ix_workflows_namespace'), 'workflows', ['namespace'], unique=False
    )

    # Update workflow_pipeline table: replace location with workflow_id FK
    op.drop_column('workflow_pipeline', 'location')
    op.add_column(
        'workflow_pipeline',
        sa.Column('workflow_id', postgresql.UUID(as_uuid=True), nullable=False),
    )
    op.create_foreign_key(
        'fk_workflow_pipeline_workflow_id',
        'workflow_pipeline',
        'workflows',
        ['workflow_id'],
        ['id'],
    )
    op.create_index(
        op.f('ix_workflow_pipeline_workflow_id'),
        'workflow_pipeline',
        ['workflow_id'],
        unique=False,
    )


def downgrade() -> None:
    # Revert workflow_pipeline table changes
    op.drop_index(
        op.f('ix_workflow_pipeline_workflow_id'), table_name='workflow_pipeline'
    )
    op.drop_constraint(
        'fk_workflow_pipeline_workflow_id', 'workflow_pipeline', type_='foreignkey'
    )
    op.drop_column('workflow_pipeline', 'workflow_id')
    op.add_column(
        'workflow_pipeline', sa.Column('location', sa.String(), nullable=False)
    )

    # Drop in reverse order (children first, then parent)
    op.drop_index(op.f('ix_workflows_namespace'), table_name='workflows')
    op.drop_index(op.f('ix_workflows_id'), table_name='workflows')
    op.drop_table('workflows')

    op.drop_index(op.f('ix_agents_namespace'), table_name='agents')
    op.drop_index(op.f('ix_agents_id'), table_name='agents')
    op.drop_table('agents')

    op.drop_index(op.f('ix_namespaces_name'), table_name='namespaces')
    op.drop_table('namespaces')
