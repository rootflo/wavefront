from datetime import datetime
import uuid

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from ..database.base import Base
from .user_group_member import UserGroupMember
from .user_group_role import UserGroupRole


class UserGroup(Base):
    """A named bundle of roles that can be handed to several users at once.

    Both links are optional: a group with no roles grants nothing, and a group
    with no members is simply unused. Neither state is an error -- an empty
    group is what an admin has right after creating one.
    """

    __tablename__ = 'user_group'

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    name: Mapped[str] = mapped_column(nullable=False, unique=True)
    description: Mapped[str] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        server_default=func.now(),
    )

    users = relationship(
        'User', secondary=UserGroupMember.__table__, back_populates='groups'
    )
    roles = relationship(
        'Role', secondary=UserGroupRole.__table__, back_populates='groups'
    )

    def to_dict(self):
        return {
            'id': str(self.id),
            'name': self.name,
            'description': self.description,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
