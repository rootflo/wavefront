import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..database.base import Base


class OAuthApp(Base):
    """Platform OAuth client credentials (client id/secret).

    Shared credential store for features that need a registered OAuth
    application (email connections today; authenticators later). This is not a
    user's mailbox — connected mailboxes live in `email_connections`.

    The client secret lives in its own encrypted column rather than inside
    `config` so the config blob can be returned to admin UIs as-is.
    """

    __tablename__ = 'oauth_apps'

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    name: Mapped[str] = mapped_column(String(length=64), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(String(length=255), nullable=True)
    provider: Mapped[str] = mapped_column(
        String(length=32),
        nullable=False,
        index=True,
        comment='possible values: gmail, outlook',
    )
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    encrypted_client_secret: Mapped[str] = mapped_column(Text, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default='true'
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default='false'
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("name !~ '\\s'", name='oauth_app_name_no_spaces'),
    )

    def to_dict(self, include_config: bool = False):
        """Secrets never leave here: `config` is opt-in and the client secret is
        only ever reported as present or absent."""
        payload = {
            'id': str(self.id),
            'name': self.name,
            'description': self.description,
            'provider': self.provider,
            'is_enabled': self.is_enabled,
            'has_client_secret': bool(self.encrypted_client_secret),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_config:
            payload['config'] = self.config
        return payload
