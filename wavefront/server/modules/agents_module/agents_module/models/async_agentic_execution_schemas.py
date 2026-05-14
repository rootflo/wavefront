import uuid
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class AsyncInferenceResponse(BaseModel):
    execution_id: uuid.UUID
    status: str = Field(default='pending')
    entity_type: str
    entity_id: uuid.UUID
    status_url: str


class AgenticExecutionStatusResponse(BaseModel):
    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    celery_task_id: Optional[str] = None
    status: str
    error: Optional[str] = None
    input_files: Optional[List[Any]] = None
    output_url: Optional[str] = None
    history_url: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
