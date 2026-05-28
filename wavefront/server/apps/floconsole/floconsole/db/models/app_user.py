import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from ..base import Base


class AppUser(Base):
    __tablename__ = 'app_user'

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('user.id', ondelete='CASCADE'), primary_key=True, nullable=False
    )
    app_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('app.id', ondelete='CASCADE'), primary_key=True, nullable=False
    )

    # Relationships
    user = relationship('User', back_populates='app_users')
    app = relationship('App', back_populates='app_users')
