import uuid
from datetime import datetime

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from ..database.base import Base


class WorkflowPipeline(Base):
    __tablename__ = 'workflow_pipeline'

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    name: Mapped[str] = mapped_column(nullable=False)
    description: Mapped[str] = mapped_column(nullable=True)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('workflows.id'), nullable=False, index=True
    )
    retry_policy: Mapped[str] = mapped_column(nullable=True)
    timeout: Mapped[int] = mapped_column(nullable=True)
    concurrency_limit: Mapped[int] = mapped_column(nullable=True, default=1)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.now, onupdate=datetime.now
    )

    # Relationship to Workflow
    workflow = relationship('Workflow', foreign_keys=[workflow_id])

    # Relationship to WorkflowRuns
    runs = relationship(
        'WorkflowRuns',
        back_populates='workflow_pipeline',
        cascade='all, delete',
    )

    def to_dict(self):
        return {
            'id': str(self.id),
            'name': self.name,
            'description': self.description,
            'workflow_id': str(self.workflow_id),
            'retry_policy': self.retry_policy,
            'timeout': self.timeout,
            'concurrency_limit': self.concurrency_limit,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }
