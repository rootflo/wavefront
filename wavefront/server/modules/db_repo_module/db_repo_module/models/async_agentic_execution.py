import uuid
from datetime import datetime

from sqlalchemy import Text
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from ..database.base import Base


class AsyncAgenticExecution(Base):
    __tablename__ = 'async_agentic_executions'

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    entity_type: Mapped[str] = mapped_column(nullable=False)  # 'agent' or 'workflow'
    entity_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    celery_task_id: Mapped[str] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(
        nullable=False, index=True
    )  # 'pending' | 'in_progress' | 'completed' | 'failed'
    input_bucket: Mapped[str] = mapped_column(nullable=True)
    inputs: Mapped[str] = mapped_column(Text, nullable=True)
    input_files: Mapped[str] = mapped_column(nullable=True)
    output_file: Mapped[str] = mapped_column(nullable=True)
    history_file: Mapped[str] = mapped_column(nullable=True)
    error: Mapped[str] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(nullable=True)
    completed_at: Mapped[datetime] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.now, onupdate=datetime.now
    )

    def to_dict(self):
        return {
            'id': str(self.id),
            'entity_type': self.entity_type,
            'entity_id': str(self.entity_id),
            'celery_task_id': self.celery_task_id,
            'status': self.status,
            'input_bucket': self.input_bucket,
            'inputs': self.inputs,
            'input_files': self.input_files,
            'output_file': self.output_file,
            'history_file': self.history_file,
            'error': self.error,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat()
            if self.completed_at
            else None,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }
