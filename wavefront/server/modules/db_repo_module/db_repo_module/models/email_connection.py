import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..database.base import Base


class EmailConnection(Base):
    """One mailbox a user connected through an `oauth_apps` registration.

    The single source of OAuth tokens for every email feature: triggers watch
    through it, agents send through it, and platform mail uses whichever row is
    flagged `is_primary`.

    `granted_scopes` records what consent actually returned, so a feature can be
    refused before an API call fails.
    """

    __tablename__ = 'email_connections'

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    name: Mapped[str] = mapped_column(String(length=255), nullable=False)
    provider: Mapped[str] = mapped_column(
        String(length=32),
        nullable=False,
        index=True,
        comment='possible values: gmail, outlook',
    )
    oauth_app_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('oauth_apps.id', ondelete='RESTRICT'),
        nullable=False,
        index=True,
    )
    mailbox_email: Mapped[str] = mapped_column(
        String(length=320), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(length=32),
        nullable=False,
        index=True,
        server_default='pending_auth',
        comment=('possible values: pending_auth, active, error, revoked, deleted'),
    )
    granted_scopes: Mapped[str] = mapped_column(Text, nullable=True)
    encrypted_refresh_token: Mapped[str] = mapped_column(Text, nullable=True)
    encrypted_access_token: Mapped[str] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime] = mapped_column(nullable=True)
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default='false'
    )
    last_error: Mapped[str] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(length=255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        # One live connection per mailbox: a second row would compete for the
        # same tokens, so scope upgrades update this row instead. Deleted rows
        # are excluded so a mailbox can be reconnected later.
        Index(
            'uq_email_connection_mailbox',
            'provider',
            'mailbox_email',
            unique=True,
            postgresql_where=text("status <> 'deleted'"),
        ),
        # Exactly one primary sender at a time, enforced by the database rather
        # than by whichever code path happens to set the flag.
        Index(
            'uq_email_connection_primary',
            'is_primary',
            unique=True,
            postgresql_where=text('is_primary'),
        ),
    )

    def to_dict(self):
        return {
            'id': str(self.id),
            'name': self.name,
            'provider': self.provider,
            'oauth_app_id': str(self.oauth_app_id),
            'mailbox_email': self.mailbox_email,
            'status': self.status,
            'granted_scopes': self.granted_scopes,
            'token_expires_at': self.token_expires_at.isoformat()
            if self.token_expires_at
            else None,
            'is_primary': self.is_primary,
            'last_error': self.last_error,
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
