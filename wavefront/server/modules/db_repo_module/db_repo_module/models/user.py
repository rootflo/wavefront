import uuid
from datetime import datetime
from typing import Optional

from db_repo_module.models.user_group_member import UserGroupMember
from db_repo_module.models.user_role import UserRole
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship
from sqlalchemy.orm import validates

from ..database.base import Base
from ..models.session import Session


class User(Base):
    __tablename__ = 'user'

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    email: Mapped[str] = mapped_column(nullable=False, unique=True)
    username: Mapped[Optional[str]] = mapped_column(nullable=True, unique=True)
    password: Mapped[str] = mapped_column(nullable=False)
    first_name: Mapped[str] = mapped_column(nullable=False)
    last_name: Mapped[str] = mapped_column(nullable=False)
    deleted: Mapped[bool] = mapped_column(default=False)

    # Account lockout fields
    failed_attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    locked_until: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    last_failed_attempt: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    # Add relationship
    roles = relationship(
        'Role',
        secondary=UserRole.__table__,
        back_populates='users',
        cascade='all, delete',
    )

    # Groups the user belongs to. No cascade: removing a user must not take the
    # shared group down with it, only their membership row (handled by the FK).
    groups = relationship(
        'UserGroup',
        secondary=UserGroupMember.__table__,
        back_populates='users',
    )

    # Add relationship for sessions
    sessions = relationship(
        Session, back_populates='user', cascade='all, delete-orphan'
    )

    @validates('email')
    def _normalize_email(self, key, address: str) -> str:
        """Persist emails in lowercase only so lookups are case-insensitive-safe."""
        if address is None:
            return address
        return str(address).strip().lower()

    def to_dict(self):
        return {
            'id': str(self.id),
            'email': self.email,
            'username': self.username,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'failed_attempts': self.failed_attempts,
            'locked_until': self.locked_until.isoformat()
            if self.locked_until
            else None,
            'last_failed_attempt': self.last_failed_attempt.isoformat()
            if self.last_failed_attempt
            else None,
            'last_login_at': self.last_login_at.isoformat()
            if self.last_login_at
            else None,
        }
