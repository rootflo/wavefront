from pydantic import BaseModel, Field, validator
from typing import Optional, Union, Any, Dict, List
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
        '',
        description='Optional welcome message spoken at call start (empty skips greeting)',
    )
    # Must be declared before tts_voice_ids so the voice-id validator can read it
    # (Pydantic v1 validators only see already-validated fields).
    supported_languages: Optional[List[str]] = Field(
        None,
        description='List of supported language codes (ISO 639-1, e.g., ["en", "hi", "te"])',
    )
    default_language: str = Field(
        'en',
        description='Default language if detection fails (must be in supported_languages)',
    )
    tts_voice_ids: Dict[str, str] = Field(
        ...,
        description='TTS voice identifiers per language (e.g., {"en": "alloy", "hi": "shimmer"})',
    )
    tts_parameters: Optional[Dict[str, Any]] = Field(
        None, description='Provider-specific TTS parameters (model, stability, etc.)'
    )
    stt_parameters: Optional[Dict[str, Any]] = Field(
        None, description='Provider-specific STT parameters (model, endpointing, etc.)'
    )
    status: VoiceAgentStatus = Field(
        default=VoiceAgentStatus.INACTIVE,
        description='Agent status (active or inactive)',
    )
    inbound_numbers: Optional[List[str]] = Field(
        None,
        description='Phone numbers for receiving inbound calls (E.164 format, globally unique)',
    )
    outbound_numbers: Optional[List[str]] = Field(
        None,
        description='Phone numbers for making outbound calls (E.164 format)',
    )

    @validator('tts_voice_ids')
    def validate_tts_voice_ids_keys(cls, v, values):
        """Validate that tts_voice_ids has voice IDs for all supported languages."""
        # Get supported languages, default to ['en'] if not provided
        supported_langs = values.get('supported_languages') or ['en']

        if not isinstance(v, dict):
            raise ValueError('tts_voice_ids must be a dictionary')

        if not v:
            raise ValueError('tts_voice_ids dictionary cannot be empty')

        # Check all languages have voice IDs
        supported_set = set(supported_langs)
        provided_set = set(v.keys())

        missing_langs = supported_set - provided_set
        if missing_langs:
            raise ValueError(
                f'Missing voice IDs for languages: {sorted(missing_langs)}'
            )

        extra_langs = provided_set - supported_set
        if extra_langs:
            raise ValueError(
                f'Voice IDs provided for unsupported languages: {sorted(extra_langs)}'
            )

        # Validate each voice_id is non-empty
        for lang, voice_id in v.items():
            if not voice_id or not str(voice_id).strip():
                raise ValueError(f'Voice ID for language "{lang}" cannot be empty')

        return v


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
    tts_voice_ids: Union[Dict[str, str], Any] = Field(default=UNSET)
    tts_parameters: Union[Dict[str, Any], None, Any] = Field(default=UNSET)
    stt_parameters: Union[Dict[str, Any], None, Any] = Field(default=UNSET)
    status: Union[VoiceAgentStatus, Any] = Field(default=UNSET)
    inbound_numbers: Union[List[str], Any] = Field(default=UNSET)
    outbound_numbers: Union[List[str], Any] = Field(default=UNSET)
    supported_languages: Union[List[str], Any] = Field(default=UNSET)
    default_language: Union[str, Any] = Field(default=UNSET)


class VoiceAgentListItem(BaseModel):
    """Compact voice agent fields for table / list views."""

    id: uuid.UUID
    name: str
    description: Optional[str]
    status: str
    supported_languages: List[str]
    default_language: str
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class VoiceAgentResponse(BaseModel):
    """Full voice agent detail (edit / operations / runtime)."""

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
    tts_voice_ids: Dict[str, str]
    tts_parameters: Optional[Dict[str, Any]]
    stt_parameters: Optional[Dict[str, Any]]
    status: str
    inbound_numbers: List[str]
    outbound_numbers: List[str]
    supported_languages: List[str]
    default_language: str
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class InitiateCallPayload(BaseModel):
    to_number: str = Field(..., description='Destination phone number (E.164 format)')
    from_number: Optional[str] = Field(
        None,
        description='Source phone number (optional, defaults to first configured number)',
    )


class CreateWebRTCRoomPayload(BaseModel):
    allowed_agent_ids: Optional[List[uuid.UUID]] = Field(
        None,
        description=(
            'Narrow the agents this browser room may hot-swap to. Only active '
            'agents ever qualify; this can remove agents, never add them. '
            'Omit to allow every active agent.'
        ),
    )
    room_context_handles_language: bool = Field(
        False,
        description=(
            'When true, the app drives the conversation language through the room '
            'context (set_context.language): the agent gets no language-switching '
            'rules and no detect_and_switch_language tool. Default false keeps the '
            "agent's native language switching."
        ),
    )
    carry_history_on_swap: bool = Field(
        True,
        description=(
            'When the room hot-swaps to another agent, carry the conversation '
            'so far (user/assistant turns) over to the new agent. Default true. '
            'Set false to start each swapped-in agent with a clean context.'
        ),
    )
