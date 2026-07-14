"""add_agent_workflow_versioning

Revision ID: 1d6a0d5cfd6f
Revises: 74c837a023f3
Create Date: 2026-07-09 11:51:09.170434

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '1d6a0d5cfd6f'
down_revision: Union[str, None] = '74c837a023f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- agents.current_version -------------------------------------------------
    op.add_column(
        'agents',
        sa.Column('current_version', sa.Integer(), nullable=False, server_default='1'),
    )
    op.alter_column('agents', 'current_version', server_default=None)

    # --- workflows.current_version ----------------------------------------------
    op.add_column(
        'workflows',
        sa.Column('current_version', sa.Integer(), nullable=False, server_default='1'),
    )
    op.alter_column('workflows', 'current_version', server_default=None)

    # --- agent_versions -----------------------------------------------------------
    op.create_table(
        'agent_versions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('agent_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column(
            'is_deleted', sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            'created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')
        ),
        sa.Column(
            'updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')
        ),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'agent_id', 'version', name='uq_agent_versions_agent_id_version'
        ),
    )
    op.create_index(
        op.f('ix_agent_versions_id'), 'agent_versions', ['id'], unique=False
    )
    op.create_index(
        op.f('ix_agent_versions_agent_id'), 'agent_versions', ['agent_id'], unique=False
    )
    op.create_index(
        op.f('ix_agent_versions_is_deleted'),
        'agent_versions',
        ['is_deleted'],
        unique=False,
    )

    # Backfill: every existing agent becomes version 1
    op.execute(
        """
        INSERT INTO agent_versions (id, agent_id, version, is_deleted, created_at, updated_at)
        SELECT gen_random_uuid(), id, 1, false, created_at, updated_at FROM agents
        """
    )

    # --- workflow_versions ----------------------------------------------------
    op.create_table(
        'workflow_versions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('workflow_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column(
            'is_deleted', sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            'created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')
        ),
        sa.Column(
            'updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')
        ),
        sa.ForeignKeyConstraint(['workflow_id'], ['workflows.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'workflow_id', 'version', name='uq_workflow_versions_workflow_id_version'
        ),
    )
    op.create_index(
        op.f('ix_workflow_versions_id'), 'workflow_versions', ['id'], unique=False
    )
    op.create_index(
        op.f('ix_workflow_versions_workflow_id'),
        'workflow_versions',
        ['workflow_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_workflow_versions_is_deleted'),
        'workflow_versions',
        ['is_deleted'],
        unique=False,
    )

    # Backfill: every existing workflow becomes version 1
    op.execute(
        """
        INSERT INTO workflow_versions (id, workflow_id, version, is_deleted, created_at, updated_at)
        SELECT gen_random_uuid(), id, 1, false, created_at, updated_at FROM workflows
        """
    )

    # --- workflow_pipeline.workflow_version ------------------------------------
    # Nullable first so we can backfill from the parent workflow's current_version,
    # then tightened to NOT NULL once every row has a value.
    op.add_column(
        'workflow_pipeline',
        sa.Column('workflow_version', sa.Integer(), nullable=True),
    )
    op.execute(
        """
        UPDATE workflow_pipeline
        SET workflow_version = w.current_version
        FROM workflows w
        WHERE workflow_pipeline.workflow_id = w.id
        """
    )
    op.alter_column('workflow_pipeline', 'workflow_version', nullable=False)


def downgrade() -> None:
    op.drop_column('workflow_pipeline', 'workflow_version')

    op.drop_index(
        op.f('ix_workflow_versions_is_deleted'), table_name='workflow_versions'
    )
    op.drop_index(
        op.f('ix_workflow_versions_workflow_id'), table_name='workflow_versions'
    )
    op.drop_index(op.f('ix_workflow_versions_id'), table_name='workflow_versions')
    op.drop_table('workflow_versions')

    op.drop_index(op.f('ix_agent_versions_is_deleted'), table_name='agent_versions')
    op.drop_index(op.f('ix_agent_versions_agent_id'), table_name='agent_versions')
    op.drop_index(op.f('ix_agent_versions_id'), table_name='agent_versions')
    op.drop_table('agent_versions')

    op.drop_column('workflows', 'current_version')
    op.drop_column('agents', 'current_version')
