import uuid
from datetime import datetime

from sqlalchemy import String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..database.base import Base


class AgenticTriggerCredential(Base):
    __tablename__ = 'agentic_trigger_credentials'

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    provider: Mapped[str] = mapped_column(
        String(length=32),
        nullable=False,
        index=True,
        comment='possible values: gmail',
    )
    external_account_id: Mapped[str] = mapped_column(
        String(length=320), nullable=False, index=True
    )
    encrypted_refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_access_token: Mapped[str] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime] = mapped_column(nullable=True)
    scopes: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            'provider', 'external_account_id', name='uq_trigger_credential_account'
        ),
    )

    def to_dict(self):
        return {
            'id': str(self.id),
            'provider': self.provider,
            'external_account_id': self.external_account_id,
            'token_expires_at': self.token_expires_at.isoformat()
            if self.token_expires_at
            else None,
            'scopes': self.scopes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
