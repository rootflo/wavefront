import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..database.base import Base


class Secret(Base):
    """Named credential that config can reference as ``${secrets.NAME}``.

    Used by API service definitions today, so their YAML holds a reference
    instead of the credential. `value` is written through `SecretCipher`, so it
    is ciphertext when envelope encryption is enabled.
    """

    __tablename__ = 'secrets'

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    name: Mapped[str] = mapped_column(String(length=128), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(String(length=255), nullable=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("name ~ '^[A-Z][A-Z0-9_]*$'", name='secret_name_upper_snake'),
    )

    def to_dict(self):
        """The value never leaves here; it is only reported as present."""
        return {
            'id': str(self.id),
            'name': self.name,
            'description': self.description,
            'has_value': bool(self.value),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
