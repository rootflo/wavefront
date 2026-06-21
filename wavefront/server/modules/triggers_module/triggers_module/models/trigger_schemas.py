from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


TriggerProviderLiteral = Literal['gmail']
TriggerEntityTypeLiteral = Literal['agent', 'workflow']
TriggerStatusLiteral = Literal['pending_auth', 'active', 'paused', 'error', 'deleted']
TriggerEventStatusLiteral = Literal['received', 'filtered_out', 'dispatched', 'failed']


class TriggerFilterConfig(BaseModel):
    subject_regex: Optional[str] = Field(
        default=None,
        description='Python regex matched against the email subject. If None, no subject filter.',
    )
    allowed_mime_types: Optional[List[str]] = Field(
        default=None,
        description='Whitelist of attachment MIME types. If None, the server default applies.',
    )


class CreateTriggerRequest(BaseModel):
    name: str
    provider: TriggerProviderLiteral
    entity_type: TriggerEntityTypeLiteral
    entity_id: UUID
    namespace: Optional[str] = None
    filter_config: TriggerFilterConfig = Field(default_factory=TriggerFilterConfig)
    provider_config: Optional[Dict[str, Any]] = None


class CreateTriggerResponse(BaseModel):
    trigger_id: UUID
    status: TriggerStatusLiteral
    consent_url: Optional[str] = Field(
        default=None,
        description='OAuth consent URL when the provider requires user authorization.',
    )


class TriggerResponse(BaseModel):
    id: UUID
    name: str
    provider: TriggerProviderLiteral
    entity_type: TriggerEntityTypeLiteral
    entity_id: UUID
    namespace: Optional[str]
    status: TriggerStatusLiteral
    filter_config: Optional[Dict[str, Any]] = None
    provider_config: Optional[Dict[str, Any]] = None
    credential_id: Optional[UUID] = None
    last_error: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class TriggerEventResponse(BaseModel):
    id: UUID
    trigger_id: UUID
    provider_event_id: str
    status: TriggerEventStatusLiteral
    execution_id: Optional[UUID] = None
    subject: Optional[str] = None
    error: Optional[str] = None
    received_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None


class GmailPubSubMessage(BaseModel):
    """The base64-decoded JSON inside `message.data` from a Pub/Sub push."""

    emailAddress: str
    historyId: int


class GmailPubSubPushPayload(BaseModel):
    """Raw Pub/Sub push wrapper. `message.data` is base64-encoded JSON."""

    class _Message(BaseModel):
        data: str
        messageId: Optional[str] = None
        publishTime: Optional[str] = None

    message: _Message
    subscription: Optional[str] = None
