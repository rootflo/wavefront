import uuid
from datetime import datetime
from typing import Optional

from db_repo_module.models.user_role import UserRole
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from ..database.base import Base
from ..models.session import Session


class User(Base):
    __tablename__ = 'user'

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    email: Mapped[str] = mapped_column(nullable=False, unique=True)
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

    # Add relationship for sessions
    sessions = relationship(
        Session, back_populates='user', cascade='all, delete-orphan'
    )

    def to_dict(self):
        return {
            'id': str(self.id),
            'email': self.email,
            'first_name': self.first_name,
            'last_name': self.last_name,
        }
