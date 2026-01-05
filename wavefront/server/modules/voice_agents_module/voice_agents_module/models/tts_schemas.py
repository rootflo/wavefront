from pydantic import BaseModel, Field
from typing import Optional, Union, Any, Dict
from enum import Enum
from datetime import datetime
import uuid

# Sentinel value for partial updates
UNSET = object()


class TtsProvider(str, Enum):
    ELEVENLABS = 'elevenlabs'
    DEEPGRAM = 'deepgram'
    CARTESIA = 'cartesia'
    AZURE = 'azure'
    GOOGLE = 'google'
    AWS = 'aws'


class CreateTtsConfigPayload(BaseModel):
    display_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description='Display name for the TTS configuration',
    )
    description: Optional[str] = Field(
        None,
        max_length=500,
        description='Optional description of the TTS configuration',
    )
    provider: TtsProvider = Field(..., description='TTS provider')
    voice_id: str = Field(..., description='Provider-specific voice identifier')
    api_key: str = Field(..., description='API key for the TTS provider')
    language: Optional[str] = Field(
        None, description='ISO 639-1 language code (optional, for multi-lingual voices)'
    )
    parameters: Optional[Dict[str, Any]] = Field(
        None, description='Provider-specific parameters as JSON object (optional)'
    )


class UpdateTtsConfigPayload(BaseModel):
    display_name: Union[str, Any] = Field(default=UNSET)
    description: Union[str, None, Any] = Field(default=UNSET)
    provider: Union[TtsProvider, Any] = Field(default=UNSET)
    voice_id: Union[str, Any] = Field(default=UNSET)
    api_key: Union[str, Any] = Field(default=UNSET)
    language: Union[str, None, Any] = Field(default=UNSET)
    parameters: Union[Dict[str, Any], None, Any] = Field(default=UNSET)


class TtsConfigResponse(BaseModel):
    id: uuid.UUID
    display_name: str
    description: Optional[str]
    provider: str
    voice_id: str
    language: Optional[str]
    parameters: Optional[Dict[str, Any]]
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
