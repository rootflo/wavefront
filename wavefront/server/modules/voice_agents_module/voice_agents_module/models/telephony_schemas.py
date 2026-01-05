from pydantic import BaseModel, Field
from typing import Optional, Union, Any, Dict, List, Literal
from enum import Enum
from datetime import datetime
import uuid

# Sentinel value for partial updates
UNSET = object()


class TelephonyProvider(str, Enum):
    TWILIO = 'twilio'


class ConnectionType(str, Enum):
    WEBSOCKET = 'websocket'
    SIP = 'sip'


class WebhookConfig(BaseModel):
    """
    Webhook configuration for call status updates.

    Used to receive Twilio status callbacks (ringing, answered, completed, etc.)
    Optional for both websocket and SIP connection types.
    """

    status_callback_url: str = Field(
        ...,
        description='URL to receive call status updates (ringing, answered, completed)',
        example='https://example.com/webhooks/call-status',
    )


class SipConfig(BaseModel):
    """
    SIP connection configuration.

    Required for SIP connection type, specifies the SIP domain and optional parameters.
    """

    sip_domain: str = Field(
        ...,
        description='SIP domain (e.g., pstn.twilio.com, example.sip.daily.co)',
        example='pstn.twilio.com',
    )
    port: Optional[int] = Field(
        None,
        description='SIP port (optional, provider-specific)',
        ge=1,
        le=65535,
        example=5061,
    )
    transport: Optional[Literal['udp', 'tcp', 'tls']] = Field(
        None, description='SIP transport protocol (optional)', example='tls'
    )


class CreateTelephonyConfigPayload(BaseModel):
    display_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description='Display name for the telephony configuration',
    )
    description: Optional[str] = Field(
        None,
        max_length=500,
        description='Optional description of the telephony configuration',
    )
    provider: TelephonyProvider = Field(
        ..., description='Telephony provider (twilio for Phase 1)'
    )
    connection_type: ConnectionType = Field(
        ..., description='Connection type (websocket or sip)'
    )
    credentials: Dict[str, Any] = Field(
        ...,
        description='Provider credentials as JSON object (e.g., {account_sid, auth_token})',
    )
    phone_numbers: List[str] = Field(
        ...,
        description='List of phone numbers available for outbound calls',
        example=['+1234567890', '+0987654321'],
    )
    webhook_config: Optional[WebhookConfig] = Field(
        None,
        description='Webhook configuration for status callbacks (optional for both connection types)',
    )
    sip_config: Optional[SipConfig] = Field(
        None, description='SIP configuration (required for SIP connection type)'
    )

    def model_post_init(self, __context):
        """Validate connection type specific requirements"""
        if self.connection_type == ConnectionType.SIP and not self.sip_config:
            raise ValueError('sip_config is required for SIP connection type')


class UpdateTelephonyConfigPayload(BaseModel):
    display_name: Union[str, Any] = Field(default=UNSET)
    description: Union[str, None, Any] = Field(default=UNSET)
    provider: Union[TelephonyProvider, Any] = Field(default=UNSET)
    connection_type: Union[ConnectionType, Any] = Field(default=UNSET)
    credentials: Union[Dict[str, Any], Any] = Field(default=UNSET)
    phone_numbers: Union[List[str], Any] = Field(default=UNSET)
    webhook_config: Union[WebhookConfig, None, Any] = Field(default=UNSET)
    sip_config: Union[SipConfig, None, Any] = Field(default=UNSET)


class TelephonyConfigResponse(BaseModel):
    id: uuid.UUID
    display_name: str
    description: Optional[str]
    provider: str
    connection_type: str
    phone_numbers: List[str]
    webhook_config: Optional[WebhookConfig]
    sip_config: Optional[SipConfig]
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
