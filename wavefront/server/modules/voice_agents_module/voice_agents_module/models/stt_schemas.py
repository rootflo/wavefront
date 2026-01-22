from pydantic import BaseModel, Field
from typing import Optional, Union, Any
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


class UpdateSttConfigPayload(BaseModel):
    display_name: Union[str, Any] = Field(default=UNSET)
    description: Union[str, None, Any] = Field(default=UNSET)
    api_key: Union[str, Any] = Field(default=UNSET)


class SttConfigResponse(BaseModel):
    id: uuid.UUID
    display_name: str
    description: Optional[str]
    provider: str
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
