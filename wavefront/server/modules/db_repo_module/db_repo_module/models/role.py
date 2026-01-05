import uuid

from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from ..database.base import Base
from .role_resource import RoleResource
from .user_role import UserRole


class Role(Base):
    __tablename__ = 'role'

    id: Mapped[str] = mapped_column(index=True, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(nullable=False)
    description: Mapped[str] = mapped_column(nullable=True)

    # Update relationships with explicit secondary models
    users = relationship('User', secondary=UserRole.__table__, back_populates='roles')
    resources = relationship(
        'Resource', secondary=RoleResource.__table__, back_populates='roles'
    )

    def to_dict(self):
        return {'id': self.id, 'name': self.name, 'description': self.description}
