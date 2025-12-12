from pydantic import BaseModel, Field
from typing import Optional, Union, Any, Dict
from enum import Enum
from datetime import datetime
import uuid

# Sentinel value for partial updates
UNSET = object()


class VoiceAgentStatus(str, Enum):
    ACTIVE = 'active'
    INACTIVE = 'inactive'


class CreateVoiceAgentPayload(BaseModel):
    name: str = Field(..., description='Name of the voice agent')
    description: Optional[str] = Field(
        None, description='Description of the voice agent'
    )
    llm_config_id: uuid.UUID = Field(..., description='LLM inference config ID')
    tts_config_id: uuid.UUID = Field(..., description='TTS config ID')
    stt_config_id: uuid.UUID = Field(..., description='STT config ID')
    telephony_config_id: uuid.UUID = Field(..., description='Telephony config ID')
    system_prompt: str = Field(..., description='System prompt for the LLM')
    conversation_config: Optional[Dict[str, Any]] = Field(
        None, description='Conversation configuration settings (optional)'
    )
    welcome_message: str = Field(
        ...,
        description='Welcome message to play at call start (will be converted to audio)',
    )
    status: VoiceAgentStatus = Field(
        default=VoiceAgentStatus.INACTIVE,
        description='Agent status (active or inactive)',
    )


class UpdateVoiceAgentPayload(BaseModel):
    name: Union[str, Any] = Field(default=UNSET)
    description: Union[str, None, Any] = Field(default=UNSET)
    llm_config_id: Union[uuid.UUID, Any] = Field(default=UNSET)
    tts_config_id: Union[uuid.UUID, Any] = Field(default=UNSET)
    stt_config_id: Union[uuid.UUID, Any] = Field(default=UNSET)
    telephony_config_id: Union[uuid.UUID, Any] = Field(default=UNSET)
    system_prompt: Union[str, Any] = Field(default=UNSET)
    conversation_config: Union[Dict[str, Any], None, Any] = Field(default=UNSET)
    welcome_message: Union[str, Any] = Field(default=UNSET)
    status: Union[VoiceAgentStatus, Any] = Field(default=UNSET)


class VoiceAgentResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str]
    llm_config_id: uuid.UUID
    tts_config_id: uuid.UUID
    stt_config_id: uuid.UUID
    telephony_config_id: uuid.UUID
    system_prompt: str
    conversation_config: Optional[Dict[str, Any]]
    welcome_message: str
    status: str
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class InitiateCallPayload(BaseModel):
    to_number: str = Field(..., description='Destination phone number (E.164 format)')
    from_number: Optional[str] = Field(
        None,
        description='Source phone number (optional, defaults to first configured number)',
    )
