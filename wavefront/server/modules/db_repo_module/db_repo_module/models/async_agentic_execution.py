import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
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
    # The raw variables the caller supplied for this run. Deliberately excludes
    # the internal `_wf_execution_id` that with_execution_variables() adds to
    # the worker payload -- the execution id is already this row's `id`.
    variables: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    input_files: Mapped[str] = mapped_column(nullable=True)
    output_file: Mapped[str] = mapped_column(nullable=True)
    history_file: Mapped[str] = mapped_column(nullable=True)
    error: Mapped[str] = mapped_column(Text, nullable=True)
    # Run parameters, kept so a failed run can be retried from the row alone.
    # Null on rows predating these columns.
    version: Mapped[Optional[int]] = mapped_column(nullable=True)
    output_json_enabled: Mapped[Optional[bool]] = mapped_column(nullable=True)
    llm_inference_config_id: Mapped[Optional[uuid.UUID]] = mapped_column(nullable=True)
    # Retry lineage. Unique so an execution is retried at most once, which also
    # keeps a chain linear: `attempt` on its newest row is the run count.
    retry_of_execution_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey('async_agentic_executions.id', ondelete='SET NULL'),
        nullable=True,
        unique=True,
    )
    attempt: Mapped[int] = mapped_column(nullable=False, default=1, server_default='1')
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
            'variables': self.variables,
            'input_files': self.input_files,
            'output_file': self.output_file,
            'history_file': self.history_file,
            'error': self.error,
            'version': self.version,
            'output_json_enabled': self.output_json_enabled,
            'llm_inference_config_id': str(self.llm_inference_config_id)
            if self.llm_inference_config_id
            else None,
            'retry_of_execution_id': str(self.retry_of_execution_id)
            if self.retry_of_execution_id
            else None,
            'attempt': self.attempt,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat()
            if self.completed_at
            else None,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }
