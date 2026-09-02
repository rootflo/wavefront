"""add index on knowledge_base_embeddings.document_id

`knowledge_base_embeddings.document_id` is a FK column with no index
(Postgres doesn't index FK columns automatically). Queries that pre-filter
`knowledge_base_documents` to a small candidate set (e.g. the repeat-pledge
`/exact-match` branch/loan_date check) then join to `knowledge_base_embeddings`
on this column -- without an index, Postgres has no cheap way to satisfy
that join and falls back to a full sequential scan of the entire embeddings
table (10M+ rows and growing) on every call, regardless of how small the
filtered candidate set is.

Built CONCURRENTLY (via an autocommit block, since CREATE/DROP INDEX
CONCURRENTLY cannot run inside a transaction) so this doesn't hold a
blocking lock against the table for the duration of the build.

Revision ID: a3f7e91b4c6d
Revises: b8d3f6a9c1e4
Create Date: 2026-09-02 18:41:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a3f7e91b4c6d'
down_revision: Union[str, None] = 'b8d3f6a9c1e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.create_index(
            'ix_kbe_document_id',
            'knowledge_base_embeddings',
            ['document_id'],
            unique=False,
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            'ix_kbe_document_id',
            table_name='knowledge_base_embeddings',
            postgresql_concurrently=True,
        )
