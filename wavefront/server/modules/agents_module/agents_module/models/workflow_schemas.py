import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class WorkflowInferenceRequest(BaseModel):
    """Request model for workflow inference"""

    variables: Dict[str, Any] | None = Field(
        default=None,
        description='Variables to pass to the workflow during inference',
        example={
            'target_language': 'Spanish',
            'tone': 'formal',
            'text_to_process': 'Welcome to our application',
        },
    )
    inputs: List[dict | str] | str = Field(
        ...,
        description='Inputs to use for inference',
        example=[
            'Process the following text: <text_to_process> with <target_language>'
        ],
    )
    output_json_enabled: bool = Field(
        default=False,
        description='Whether to extract JSON from workflow response. If False, returns raw string output.',
    )
    listen_events: bool = Field(
        default=False,
        description='Whether to enable real-time event streaming via WebSocket during workflow execution.',
    )


class WorkflowInferenceResponse(BaseModel):
    """Response model for workflow inference"""

    result: str | Dict = Field(
        ..., description='The inference result from the workflow'
    )
    workflow_id: str = Field(
        ..., description='The ID of the workflow that performed the inference'
    )
    namespace: str = Field(
        ..., description='The namespace of the workflow that performed the inference'
    )
    execution_time: float = Field(..., description='Execution time in seconds')


class WorkflowResponse(BaseModel):
    """Response model for single workflow with YAML content"""

    id: uuid.UUID = Field(..., description='The unique UUID of the workflow')
    name: str = Field(..., description='The unique name of the workflow')
    namespace: str = Field(..., description='The namespace of the workflow')
    yaml_content: str = Field(
        ..., description='YAML configuration content of the workflow'
    )
    created_at: str = Field(..., description='Creation timestamp in ISO format')
    updated_at: str = Field(..., description='Last update timestamp in ISO format')


class WorkflowListItem(BaseModel):
    """Response model for workflow metadata in list operations (without YAML)"""

    id: uuid.UUID = Field(..., description='The unique UUID of the workflow')
    name: str = Field(..., description='The unique name of the workflow')
    namespace: str = Field(..., description='The namespace of the workflow')
    created_at: str = Field(..., description='Creation timestamp in ISO format')
    updated_at: str = Field(..., description='Last update timestamp in ISO format')


class WorkflowsListResponse(BaseModel):
    """Response model for listing multiple workflows"""

    workflows: List[WorkflowListItem] = Field(
        ..., description='List of workflow metadata'
    )
    count: int = Field(..., description='Total number of workflows returned')


class WorkflowEventMessage(BaseModel):
    """Model for WebSocket workflow event messages"""

    event_type: str = Field(..., description='Type of workflow event')
    timestamp: float = Field(..., description='Unix timestamp when the event occurred')
    workflow_id: str = Field(..., description='ID of the workflow generating the event')
    namespace: str = Field(..., description='Namespace of the workflow')
    node_name: Optional[str] = Field(
        None, description='Name of the node involved in the event'
    )
    node_type: Optional[str] = Field(
        None, description='Type of node (agent, tool, start, end)'
    )
    execution_time: Optional[float] = Field(
        None, description='Time taken for node execution in seconds'
    )
    error: Optional[str] = Field(
        None, description='Error message if event represents a failure'
    )
    router_choice: Optional[str] = Field(
        None, description='Node chosen by router decision'
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None, description='Additional event-specific data'
    )
