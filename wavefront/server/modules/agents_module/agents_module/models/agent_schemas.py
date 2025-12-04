import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AgentInferenceRequest(BaseModel):
    """Request model for agent inference"""

    variables: Dict[str, Any] | None = Field(
        default=None,
        description='Variables to pass to the agent during inference',
        example={
            'target_language': 'Spanish',
            'tone': 'formal',
            'text_to_translate': 'Welcome to our application',
        },
    )
    inputs: List[dict | str] | str = Field(
        ...,
        description='Inputs to use for inference',
        example=[
            'Translate the following text: <text_to_translate> to <target_language>'
        ],
    )
    llm_inference_config_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Optional ID of LLM inference configuration to override agent's default LLM",
    )
    output_json_enabled: bool = Field(
        default=True,
        description='Whether to extract JSON from agent response. If False, returns raw string output.',
    )
    tool_names: Optional[List[str]] = Field(
        default=None,
        description='Optional list of tool names to load and make available to the agent during inference',
        example=['bigquery_test_connection', 'bigquery_fetch_data'],
    )


class AgentInferenceResponse(BaseModel):
    """Response model for agent inference"""

    result: str = Field(..., description='The inference result from the agent')
    agent_id: str = Field(
        ..., description='The ID of the agent that performed the inference'
    )
    namespace: str = Field(
        ..., description='The namespace of the agent that performed the inference'
    )
    execution_time: float = Field(..., description='Execution time in seconds')


class AgentResponse(BaseModel):
    """Response model for single agent with YAML content"""

    id: uuid.UUID = Field(..., description='The unique UUID of the agent')
    name: str = Field(..., description='The unique name of the agent')
    namespace: str = Field(..., description='The namespace of the agent')
    yaml_content: str = Field(
        ..., description='YAML configuration content of the agent'
    )
    created_at: str = Field(..., description='Creation timestamp in ISO format')
    updated_at: str = Field(..., description='Last update timestamp in ISO format')


class AgentListItem(BaseModel):
    """Response model for agent metadata in list operations (without YAML)"""

    id: uuid.UUID = Field(..., description='The unique UUID of the agent')
    name: str = Field(..., description='The unique name of the agent')
    namespace: str = Field(..., description='The namespace of the agent')
    created_at: str = Field(..., description='Creation timestamp in ISO format')
    updated_at: str = Field(..., description='Last update timestamp in ISO format')


class AgentsListResponse(BaseModel):
    """Response model for listing multiple agents"""

    agents: List[AgentListItem] = Field(..., description='List of agent metadata')
    count: int = Field(..., description='Total number of agents returned')
