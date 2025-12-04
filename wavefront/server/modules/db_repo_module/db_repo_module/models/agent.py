import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database.base import Base


class Agent(Base):
    __tablename__ = 'agents'
    __table_args__ = (
        UniqueConstraint('name', 'namespace', name='uq_agents_name_namespace'),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    name: Mapped[str] = mapped_column(String(length=255), nullable=False)
    namespace: Mapped[str] = mapped_column(
        ForeignKey('namespaces.name'), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now()
    )

    @staticmethod
    def get_table_name():
        return (Agent()).__tablename__

    def to_dict(self):
        return {
            'id': str(self.id),
            'name': self.name,
            'namespace': self.namespace,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }
