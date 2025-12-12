import uuid
from datetime import datetime

from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship
from sqlalchemy import ForeignKey

from ..database.base import Base


class WorkflowRuns(Base):
    __tablename__ = 'workflow_runs'

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    workflow_pipeline_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('workflow_pipeline.id', ondelete='CASCADE'), nullable=False
    )
    status: Mapped[str] = mapped_column(
        nullable=False
    )  # initiated, in_progress, completed, failed
    start_time: Mapped[datetime] = mapped_column(nullable=False)
    end_time: Mapped[datetime] = mapped_column(nullable=True)
    error: Mapped[str] = mapped_column(nullable=True)
    output: Mapped[str] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.now, onupdate=datetime.now
    )

    workflow_pipeline = relationship('WorkflowPipeline', back_populates='runs')

    def to_dict(self):
        return {
            'id': str(self.id),
            'workflow_pipeline_id': str(self.workflow_pipeline_id),
            'status': self.status,
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'error': self.error,
            'output': self.output,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }
