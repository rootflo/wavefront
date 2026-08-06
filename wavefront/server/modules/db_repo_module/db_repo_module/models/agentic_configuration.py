import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..database.base import Base


class AgenticConfiguration(Base):
    """Static reference data read at workflow execution time.

    Thresholds, limits, lookup tables — anything a deterministic step needs but
    should not have baked into its code or sent on every request.
    `value` is an arbitrary JSON document; wavefront never interprets it.

    Distinct from the `config` table, which holds the app's own white-labelling
    settings under a single flat key.
    """

    __tablename__ = 'agentic_configurations'
    __table_args__ = (
        UniqueConstraint(
            'namespace', 'key', name='uq_agentic_configurations_namespace_key'
        ),
    )

    # Surrogate. Lookups address a row by (namespace, key); this exists so a
    # config can be referenced stably if its key is ever renamed.
    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    namespace: Mapped[str] = mapped_column(
        ForeignKey('namespaces.name'), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(length=255), nullable=False)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now()
    )

    @staticmethod
    def get_table_name():
        return AgenticConfiguration.__tablename__

    def to_dict(self):
        return {
            'id': str(self.id),
            'namespace': self.namespace,
            'key': self.key,
            'value': self.value,
            'description': self.description,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }
