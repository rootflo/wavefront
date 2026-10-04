"""restrict knowledge base type to text / image

Revision ID: d1f6a8b3c247
Revises: b4e9c7d21a63
Create Date: 2026-10-03 10:00:00.000000

knowledge_bases.type was a free-text label. It now decides the embedding
models and the files a knowledge base accepts, so it must be one of:
  text   BGE-M3 text embeddings: vector_size 1024, no vector_size_1
  image  CLIP + DINOv3:          vector_size 512, vector_size_1 1024

Existing rows are classified by what they were configured to store: a second
vector size (vector_size_1) means CLIP + DINO, so `image`; anything else is
`text`. The free-text label is overwritten, and vector sizes are reset to the
type's, since they are now derived from it. A CHECK constraint then rejects
any other type.

Downgrade drops the constraint; the original labels and sizes are not
restored.
"""

from typing import Sequence, Union

from alembic import op


revision: str = 'd1f6a8b3c247'
down_revision: Union[str, None] = 'b4e9c7d21a63'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE knowledge_bases
        SET type = CASE
                WHEN vector_size_1 IS NOT NULL AND vector_size_1 > 0 THEN 'image'
                ELSE 'text'
            END
        """
    )
    op.execute(
        """
        UPDATE knowledge_bases
        SET vector_size = CASE WHEN type = 'image' THEN 512 ELSE 1024 END,
            vector_size_1 = CASE WHEN type = 'image' THEN 1024 ELSE NULL END
        """
    )
    op.create_check_constraint(
        'ck_knowledge_bases_type', 'knowledge_bases', "type IN ('text', 'image')"
    )


def downgrade() -> None:
    op.drop_constraint('ck_knowledge_bases_type', 'knowledge_bases', type_='check')
