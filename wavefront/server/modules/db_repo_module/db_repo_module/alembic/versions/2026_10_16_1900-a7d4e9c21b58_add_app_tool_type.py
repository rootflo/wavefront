"""add_app_tool_type

Adds the 'app' value to tool_type_enum. App tools are executed by the browser
app: call_processing forwards the LLM tool call as an event and waits for an ack.

Revision ID: a7d4e9c21b58
Revises: e2a7c5d81f94
Create Date: 2026-10-16 19:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a7d4e9c21b58'
down_revision: Union[str, None] = 'e2a7c5d81f94'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction block on older
    # Postgres versions, so run it in an autocommit block.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE tool_type_enum ADD VALUE IF NOT EXISTS 'app'")


def downgrade() -> None:
    # Postgres cannot drop a single enum value; leaving 'app' in place is harmless.
    pass
