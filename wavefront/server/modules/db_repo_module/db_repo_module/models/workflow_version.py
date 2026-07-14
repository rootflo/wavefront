import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database.base import Base


class WorkflowVersion(Base):
    __tablename__ = 'workflow_versions'
    __table_args__ = (
        UniqueConstraint(
            'workflow_id', 'version', name='uq_workflow_versions_workflow_id_version'
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('workflows.id', ondelete='CASCADE'), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(nullable=False)
    is_deleted: Mapped[bool] = mapped_column(nullable=False, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now()
    )

    @staticmethod
    def get_table_name():
        return (WorkflowVersion()).__tablename__

    def to_dict(self):
        return {
            'id': str(self.id),
            'workflow_id': str(self.workflow_id),
            'version': self.version,
            'is_deleted': self.is_deleted,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }
