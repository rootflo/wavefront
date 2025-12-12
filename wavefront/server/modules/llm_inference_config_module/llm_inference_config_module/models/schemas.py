import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional, Union

from pydantic import BaseModel, Field

# Sentinel value to distinguish between "not provided" and "explicitly null"
UNSET = object()


class InferenceEngineType(str, Enum):
    GEMINI = 'gemini'
    OPENAI = 'openai'
    OLLAMA = 'ollama'
    VLLM = 'vllm'
    ANTHROPIC = 'anthropic'
    AZURE_OPENAI = 'azure_openai'
    GROQ = 'groq'


class CreateLlmInferenceConfigPayload(BaseModel):
    llm_model: str = Field(..., description='The name/identifier of the LLM model')
    display_name: str = Field(
        ..., description='Human-readable display name for the configuration'
    )
    api_key: Optional[str] = Field(
        None, description='API key for the inference engine (optional)'
    )
    type: InferenceEngineType = Field(..., description='Type of inference engine')
    base_url: Optional[str] = Field(
        None, description='Base URL for the inference API (optional)'
    )
    parameters: Optional[Dict[str, Any]] = Field(
        None, description='LLM parameters like temperature, max_tokens, etc. (optional)'
    )


class UpdateLlmInferenceConfigPayload(BaseModel):
    llm_model: Union[str, Any] = Field(
        default=UNSET, description='The name/identifier of the LLM model'
    )
    display_name: Union[str, Any] = Field(
        default=UNSET, description='Human-readable display name for the configuration'
    )
    api_key: Union[str, None, Any] = Field(
        default=UNSET, description='API key for the inference engine'
    )
    type: Union[InferenceEngineType, Any] = Field(
        default=UNSET, description='Type of inference engine'
    )
    base_url: Union[str, None, Any] = Field(
        default=UNSET, description='Base URL for the inference API'
    )
    parameters: Union[Optional[Dict[str, Any]], Any] = Field(
        default=UNSET, description='LLM parameters like temperature, max_tokens, etc.'
    )


class LlmInferenceConfigResponse(BaseModel):
    id: uuid.UUID
    llm_model: str
    display_name: str
    type: str
    base_url: Optional[str]
    parameters: Optional[Dict[str, Any]]
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
