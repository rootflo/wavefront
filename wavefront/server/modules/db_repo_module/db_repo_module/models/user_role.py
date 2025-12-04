from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from ..database.base import Base


class UserRole(Base):
    __tablename__ = 'user_role'

    user_id: Mapped[str] = mapped_column(
        ForeignKey('user.id', ondelete='CASCADE'), primary_key=True
    )
    role_id: Mapped[str] = mapped_column(
        ForeignKey('role.id', ondelete='CASCADE'), primary_key=True
    )
