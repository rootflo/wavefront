from pydantic import BaseModel, Field, field_validator
from typing import Optional, Union, Any
from enum import Enum
from datetime import datetime
import uuid

# Sentinel value for partial updates
UNSET = object()

API_KEY_MAX_LENGTH = 512


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
    api_key: str = Field(
        ..., max_length=API_KEY_MAX_LENGTH, description='API key for the TTS provider'
    )
    region: Optional[str] = Field(
        None, description='Region for the TTS provider (e.g. Azure region)'
    )


class UpdateTtsConfigPayload(BaseModel):
    display_name: Union[str, Any] = Field(default=UNSET)
    description: Union[str, None, Any] = Field(default=UNSET)
    api_key: Union[str, Any] = Field(default=UNSET)
    region: Union[str, None, Any] = Field(default=UNSET)

    @field_validator('api_key')
    @classmethod
    def _api_key_max_length(cls, value):
        if isinstance(value, str) and len(value) > API_KEY_MAX_LENGTH:
            raise ValueError(f'api_key must be at most {API_KEY_MAX_LENGTH} characters')
        return value


class TtsConfigResponse(BaseModel):
    id: uuid.UUID
    display_name: str
    description: Optional[str]
    provider: str
    region: Optional[str]
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
