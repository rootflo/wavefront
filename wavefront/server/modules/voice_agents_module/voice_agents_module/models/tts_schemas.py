from pydantic import BaseModel, Field
from typing import Optional, Union, Any
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
    SARVAM = 'sarvam'


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
    api_key: str = Field(..., description='API key for the TTS provider')


class UpdateTtsConfigPayload(BaseModel):
    display_name: Union[str, Any] = Field(default=UNSET)
    description: Union[str, None, Any] = Field(default=UNSET)
    api_key: Union[str, Any] = Field(default=UNSET)


class TtsConfigResponse(BaseModel):
    id: uuid.UUID
    display_name: str
    description: Optional[str]
    provider: str
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
