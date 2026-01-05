from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from ..database.base import Base


class RoleResource(Base):
    __tablename__ = 'role_resource'

    role_id: Mapped[str] = mapped_column(
        ForeignKey('role.id', ondelete='CASCADE'), primary_key=True
    )
    resource_id: Mapped[str] = mapped_column(
        ForeignKey('resource.id', ondelete='CASCADE'), primary_key=True
    )
