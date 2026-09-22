"""lowercase user emails for case-insensitive auth

Revision ID: f8c2a91e4b07
Revises: e5b71c0a9d34
Create Date: 2026-09-22 21:45:00.000000

Floware now stores and looks up emails in lowercase only. Existing rows may
still have mixed-case addresses; without this data migration, a login that
lowercases the credential would miss those rows and lock users out.

Conflicts: if two distinct rows already differ only by case (e.g. A@x.com and
a@x.com), lowercasing would violate the unique constraint. The upgrade fails
loudly in that case so ops can resolve the duplicates before re-running.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f8c2a91e4b07'
down_revision: Union[str, None] = 'e5b71c0a9d34'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    conflicts = conn.execute(
        sa.text(
            """
            SELECT lower(email) AS normalized, count(*) AS cnt
            FROM "user"
            GROUP BY lower(email)
            HAVING count(*) > 1
            """
        )
    ).fetchall()
    if conflicts:
        samples = ', '.join(f'{row.normalized} ({row.cnt})' for row in conflicts[:10])
        raise RuntimeError(
            'Cannot lowercase user.email: case-only duplicate(s) exist. '
            f'Resolve these addresses first: {samples}'
        )

    op.execute(
        sa.text(
            """
            UPDATE "user"
            SET email = lower(email)
            WHERE email <> lower(email)
            """
        )
    )


def downgrade() -> None:
    # Irreversible: original casing is not retained.
    pass
