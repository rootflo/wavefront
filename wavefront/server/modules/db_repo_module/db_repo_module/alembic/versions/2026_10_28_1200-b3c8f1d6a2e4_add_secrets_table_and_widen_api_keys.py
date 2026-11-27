"""add_secrets_table_and_widen_api_keys

Adds the `secrets` table that API service definitions reference as
``${secrets.NAME}``, and widens the api_key columns to Text so they can hold
envelope ciphertext (`enc:v1:...` is far longer than 512 characters).

Schema only: existing values are not touched. Converting them between
plaintext and ciphertext is done by scripts/migrate_secrets.py.

Revision ID: b3c8f1d6a2e4
Revises: a7d4e9c21b58
Create Date: 2026-10-28 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b3c8f1d6a2e4'
down_revision: Union[str, None] = 'a7d4e9c21b58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_API_KEY_TABLES = ('llm_inference_config', 'stt_configs', 'tts_configs')


def upgrade() -> None:
    op.create_table(
        'secrets',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_secret_name'),
        sa.CheckConstraint(
            "name ~ '^[A-Z][A-Z0-9_]*$'", name='secret_name_upper_snake'
        ),
    )
    op.create_index(op.f('ix_secrets_id'), 'secrets', ['id'], unique=False)

    for table in _API_KEY_TABLES:
        op.alter_column(
            table,
            'api_key',
            type_=sa.Text(),
            existing_type=sa.String(length=512),
        )


def downgrade() -> None:
    # Fails if any api_key is longer than 512 characters, i.e. still encrypted;
    # run scripts/migrate_secrets.py --decrypt before downgrading.
    for table in _API_KEY_TABLES:
        op.alter_column(
            table,
            'api_key',
            type_=sa.String(length=512),
            existing_type=sa.Text(),
        )

    op.drop_index(op.f('ix_secrets_id'), table_name='secrets')
    op.drop_table('secrets')
