import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AsyncInferenceResponse(BaseModel):
    execution_id: uuid.UUID
    status: str = Field(default='pending')
    entity_type: str
    entity_id: uuid.UUID
    status_url: str
    variables: Optional[Dict[str, Any]] = None
    retry_of_execution_id: Optional[uuid.UUID] = None
    attempt: int = 1


class AgenticExecutionStatusResponse(BaseModel):
    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    celery_task_id: Optional[str] = None
    status: str
    # Non-null exactly when the execution failed, but the text is the raw
    # exception string only for an admin asking with ?show_error=true. Everyone
    # else gets a fixed generic message — the shape stays the same, so a client
    # can keep rendering this field either way.
    error: Optional[str] = None
    variables: Optional[Dict[str, Any]] = None
    input_files: Optional[List[Any]] = None
    version: Optional[int] = None
    retry_of_execution_id: Optional[uuid.UUID] = None
    attempt: int = 1
    # Computed on read, not stored. A failed execution can be not retryable
    # because it was already retried (see retried_by_execution_id) or because
    # it reached the attempt cap.
    is_retryable: bool = False
    retried_by_execution_id: Optional[uuid.UUID] = None
    output_url: Optional[str] = None
    history_url: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
