from .factory import EmailProviderFactory, get_email_provider_factory
from .gmail import GmailAppConfig, GmailProvider, GmailWatchConfig
from .helper import (
    build_graph_message,
    build_mime_message,
    capabilities_from_scopes,
    encode_raw_message,
    html_to_text,
    resolve_scopes,
)
from .outlook import OutlookAppConfig, OutlookProvider
from .types import (
    Attachment,
    EmailCapability,
    EmailProviderABC,
    EmailProviderError,
    EmailProviderType,
    NormalizedEmail,
    OutboundMessage,
    PushSignatureError,
    TokenBundle,
)

__all__ = [
    'Attachment',
    'EmailCapability',
    'EmailProviderABC',
    'EmailProviderError',
    'EmailProviderFactory',
    'EmailProviderType',
    'GmailAppConfig',
    'GmailProvider',
    'GmailWatchConfig',
    'NormalizedEmail',
    'OutboundMessage',
    'OutlookAppConfig',
    'OutlookProvider',
    'PushSignatureError',
    'TokenBundle',
    'build_graph_message',
    'build_mime_message',
    'capabilities_from_scopes',
    'encode_raw_message',
    'get_email_provider_factory',
    'html_to_text',
    'resolve_scopes',
]
