"""create_voice_agent_tools_tables

Revision ID: a5b3c4d5e6f7
Revises: 6010e49da528
Create Date: 2026-01-13 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a5b3c4d5e6f7'
down_revision: Union[str, None] = '6010e49da528'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum type for tool_type (check if it exists first)
    connection = op.get_bind()

    # Check if enum type already exists
    result = connection.execute(
        sa.text("SELECT 1 FROM pg_type WHERE typname = 'tool_type_enum'")
    ).fetchone()

    if not result:
        tool_type_enum = postgresql.ENUM(
            'api', 'python', name='tool_type_enum', create_type=True
        )
        tool_type_enum.create(connection, checkfirst=False)

    # Use the enum type (whether we just created it or it already existed)
    tool_type_enum = postgresql.ENUM(
        'api', 'python', name='tool_type_enum', create_type=False
    )

    # Get inspector to check for existing tables
    inspector = sa.inspect(connection)
    existing_tables = inspector.get_table_names()

    # Create voice_agent_tools table if it doesn't exist
    if 'voice_agent_tools' not in existing_tables:
        op.create_table(
            'voice_agent_tools',
            sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('display_name', sa.String(length=255), nullable=False),
            sa.Column('description', sa.Text(), nullable=False),
            sa.Column('tool_type', tool_type_enum, nullable=False),
            sa.Column(
                'config', postgresql.JSONB(astext_type=sa.Text()), nullable=False
            ),
            sa.Column(
                'parameter_schema',
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
            sa.Column('response_template', sa.Text(), nullable=True),
            sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column(
                'is_deleted', sa.Boolean(), nullable=False, server_default='false'
            ),
            sa.Column(
                'created_at',
                sa.DateTime(),
                nullable=False,
                server_default=sa.text('now()'),
            ),
            sa.Column(
                'updated_at',
                sa.DateTime(),
                nullable=False,
                server_default=sa.text('now()'),
            ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('name', name='uq_voice_agent_tool_name'),
        )
        op.create_index(
            op.f('ix_voice_agent_tools_id'), 'voice_agent_tools', ['id'], unique=False
        )
        op.create_index(
            op.f('ix_voice_agent_tools_name'),
            'voice_agent_tools',
            ['name'],
            unique=True,
        )
    else:
        print("Table 'voice_agent_tools' already exists, skipping creation")

    # Create voice_agent_tool_associations table if it doesn't exist
    if 'voice_agent_tool_associations' not in existing_tables:
        op.create_table(
            'voice_agent_tool_associations',
            sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('voice_agent_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('tool_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column(
                'is_enabled', sa.Boolean(), nullable=False, server_default='true'
            ),
            sa.Column(
                'config_overrides',
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
            sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),
            sa.Column(
                'created_at',
                sa.DateTime(),
                nullable=False,
                server_default=sa.text('now()'),
            ),
            sa.Column(
                'updated_at',
                sa.DateTime(),
                nullable=False,
                server_default=sa.text('now()'),
            ),
            sa.ForeignKeyConstraint(
                ['voice_agent_id'], ['voice_agents.id'], ondelete='CASCADE'
            ),
            sa.ForeignKeyConstraint(
                ['tool_id'], ['voice_agent_tools.id'], ondelete='CASCADE'
            ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint(
                'voice_agent_id', 'tool_id', name='uq_voice_agent_tool'
            ),
        )
        op.create_index(
            op.f('ix_voice_agent_tool_associations_id'),
            'voice_agent_tool_associations',
            ['id'],
            unique=False,
        )
        op.create_index(
            op.f('ix_voice_agent_tool_associations_voice_agent_id'),
            'voice_agent_tool_associations',
            ['voice_agent_id'],
            unique=False,
        )
        op.create_index(
            op.f('ix_voice_agent_tool_associations_tool_id'),
            'voice_agent_tool_associations',
            ['tool_id'],
            unique=False,
        )
    else:
        print("Table 'voice_agent_tool_associations' already exists, skipping creation")


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_index(
        op.f('ix_voice_agent_tool_associations_tool_id'),
        table_name='voice_agent_tool_associations',
    )
    op.drop_index(
        op.f('ix_voice_agent_tool_associations_voice_agent_id'),
        table_name='voice_agent_tool_associations',
    )
    op.drop_index(
        op.f('ix_voice_agent_tool_associations_id'),
        table_name='voice_agent_tool_associations',
    )
    op.drop_table('voice_agent_tool_associations')

    op.drop_index(op.f('ix_voice_agent_tools_name'), table_name='voice_agent_tools')
    op.drop_index(op.f('ix_voice_agent_tools_id'), table_name='voice_agent_tools')
    op.drop_table('voice_agent_tools')

    # Only drop enum type if no other columns are using it
    connection = op.get_bind()
    result = connection.execute(
        sa.text("""
            SELECT COUNT(*)
            FROM pg_attribute a
            JOIN pg_type t ON a.atttypid = t.oid
            WHERE t.typname = 'tool_type_enum'
        """)
    ).fetchone()

    # Only drop the enum if no columns are using it
    if result and result[0] == 0:
        tool_type_enum = postgresql.ENUM('api', 'python', name='tool_type_enum')
        tool_type_enum.drop(op.get_bind(), checkfirst=True)
