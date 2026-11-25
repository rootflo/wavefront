from typing import Any, Literal

from pydantic import BaseModel, Field

JobStatus = Literal['active', 'paused', 'running', 'failed', 'completed']
# email_dynamic_query: run queries and email results.
# scheduled_query: run queries on schedule and discard results.
JobType = Literal['email_dynamic_query', 'scheduled_query']


class CreateScheduledJobRequest(BaseModel):
    job_type: JobType = Field(default='email_dynamic_query')
    cron_expr: str
    timezone: str = Field(default='UTC')
    payload: dict[str, Any]
    max_retries: int = Field(default=3, ge=0, le=10)


class UpdateScheduledJobRequest(BaseModel):
    cron_expr: str | None = None
    timezone: str | None = None
    payload: dict[str, Any] | None = None
    max_retries: int | None = Field(default=None, ge=0, le=10)
    status: JobStatus | None = None
