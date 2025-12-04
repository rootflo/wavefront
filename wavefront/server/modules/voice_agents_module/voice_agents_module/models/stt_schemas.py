from pydantic import BaseModel, Field
from typing import Optional, Union, Any, Dict
from enum import Enum
from datetime import datetime
import uuid

# Sentinel value for partial updates
UNSET = object()


class SttProvider(str, Enum):
    DEEPGRAM = 'deepgram'
    ASSEMBLYAI = 'assemblyai'
    WHISPER = 'whisper'
    GOOGLE = 'google'
    AZURE = 'azure'


class CreateSttConfigPayload(BaseModel):
    display_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description='Display name for the STT configuration',
    )
    description: Optional[str] = Field(
        None,
        max_length=500,
        description='Optional description of the STT configuration',
    )
    provider: SttProvider = Field(..., description='STT provider')
    api_key: str = Field(..., description='API key for the STT provider')
    language: Optional[str] = Field(
        None,
        description='ISO 639-1 language code (optional, most providers auto-detect)',
    )
    parameters: Optional[Dict[str, Any]] = Field(
        None, description='Provider-specific parameters as JSON object (optional)'
    )


class UpdateSttConfigPayload(BaseModel):
    display_name: Union[str, Any] = Field(default=UNSET)
    description: Union[str, None, Any] = Field(default=UNSET)
    provider: Union[SttProvider, Any] = Field(default=UNSET)
    api_key: Union[str, Any] = Field(default=UNSET)
    language: Union[str, None, Any] = Field(default=UNSET)
    parameters: Union[Dict[str, Any], None, Any] = Field(default=UNSET)


class SttConfigResponse(BaseModel):
    id: uuid.UUID
    display_name: str
    description: Optional[str]
    provider: str
    language: Optional[str]
    parameters: Optional[Dict[str, Any]]
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
