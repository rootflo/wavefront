from datetime import datetime
from enum import Enum
import json
import uuid

from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from ..database.base import Base
from .role_resource import RoleResource


class ResourceScope(str, Enum):
    DATA = 'data'
    DASHBOARD = 'dashboard'
    CONSOLE = 'console'


class Resource(Base):
    __tablename__ = 'resource'

    id: Mapped[str] = mapped_column(primary_key=True, index=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(nullable=False)
    value: Mapped[str] = mapped_column(nullable=False)
    description: Mapped[str] = mapped_column(nullable=True)
    scope: Mapped[str] = mapped_column(nullable=False)
    meta: Mapped[str] = mapped_column(nullable=True)

    # Update relationship with explicit secondary model
    roles = relationship(
        'Role', secondary=RoleResource.__table__, back_populates='resources'
    )

    __table_args__ = (UniqueConstraint('key', 'value', name='key_value'),)

    def to_dict(self):
        result = {}
        for column in self.__table__.columns:
            value = getattr(self, column.name)
            if isinstance(value, uuid.UUID):
                result[column.name] = str(value)
            elif isinstance(value, datetime):
                result[column.name] = value.isoformat()
            elif column.name == 'meta':
                result[column.name] = json.loads(value) if value else None
            else:
                result[column.name] = value
        return result

    @staticmethod
    def get_table_name():
        return (Resource()).__tablename__
