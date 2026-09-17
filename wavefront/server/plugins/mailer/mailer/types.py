from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence


class EmailProviderType(Enum):
    GMAIL = 'gmail'
    OUTLOOK = 'outlook'

    def __str__(self):
        return self.value


class EmailCapability(Enum):
    """What a connection is allowed to do with a mailbox.

    Callers request capabilities; each provider translates them into its own
    scope strings. This keeps scope literals out of services and lets a
    connection be checked against what it was actually granted.
    """

    READ = 'read'
    SEND = 'send'
    MODIFY = 'modify'

    def __str__(self):
        return self.value


class EmailProviderError(Exception):
    """Provider-side failure that callers are expected to surface, not retry."""


class PushSignatureError(EmailProviderError):
    """The push notification could not be attributed to the provider."""


@dataclass
class TokenBundle:
    refresh_token: Optional[str]
    access_token: Optional[str]
    expires_at: Optional[datetime]
    scopes: Optional[str]
    external_account_id: str


@dataclass
class Attachment:
    file_name: str
    mime_type: str
    content_bytes: bytes


@dataclass
class OutboundMessage:
    subject: str
    body_html: str
    to: List[str]
    attachments: List[Attachment] = field(default_factory=list)
    sender_display_name: Optional[str] = None


@dataclass
class NormalizedEmail:
    provider_event_id: str
    subject: str
    sender: Optional[str]
    body_text: str
    attachments: List[Attachment] = field(default_factory=list)


class EmailProviderABC(ABC):
    """Everything a connected mailbox can do, for one provider.

    Instances are built from a single OAuth application's configuration, so the
    client credentials live here while the per-mailbox tokens are passed in by
    the caller on every call.
    """

    provider_type: EmailProviderType

    # ---- Scopes ---------------------------------------------------------

    @abstractmethod
    def scopes_for(self, capabilities: Sequence[EmailCapability]) -> List[str]:
        """Provider scope strings for the requested capabilities, including any
        identity scopes needed to resolve the mailbox address."""

    @abstractmethod
    def capabilities_for(self, granted_scopes: Optional[str]) -> List[EmailCapability]:
        """Inverse of `scopes_for`: what a stored scope string actually permits."""

    # ---- OAuth ----------------------------------------------------------

    @abstractmethod
    def build_consent_url(self, state: str, scopes: Sequence[str]) -> str:
        """Consent URL that returns a refresh token and preserves prior grants."""

    @abstractmethod
    async def exchange_code(self, code: str) -> TokenBundle:
        """Trade an authorization code for tokens, resolving the mailbox address."""

    @abstractmethod
    async def refresh_access_token(self, refresh_token: str) -> TokenBundle:
        """Mint a fresh access token. `external_account_id` may come back empty:
        the refresh response does not identify the account."""

    @abstractmethod
    async def get_account_email(self, access_token: str) -> Optional[str]:
        """Address of the mailbox the token belongs to."""

    # ---- Mailbox operations ---------------------------------------------

    @abstractmethod
    async def send_message(
        self,
        access_token: str,
        mailbox: str,
        message: OutboundMessage,
    ) -> Optional[str]:
        """Send `message` as `mailbox`. Returns the provider message id if given."""

    @abstractmethod
    async def get_message(
        self,
        access_token: str,
        mailbox: str,
        message_id: str,
    ) -> NormalizedEmail:
        """Fetch and normalize one message, attachments included."""

    # ---- Watch subscriptions --------------------------------------------

    @abstractmethod
    async def start_watch(
        self,
        access_token: str,
        mailbox: str,
        watch_key: str,
        *,
        watch_config: Optional[Any] = None,
        push_endpoint_params: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Register the upstream watch. Returns the config to persist.

        `watch_key` names provider-side resources (Gmail: the Pub/Sub topic and
        subscription), so it must be stable for the lifetime of the watch.

        `watch_config` is provider-specific platform plumbing (Gmail: Pub/Sub
        project, push endpoint template, OIDC SA). It is owned by triggers, not
        by the OAuth app. `push_endpoint_params` fills that template.
        """

    @abstractmethod
    async def renew_watch(
        self,
        access_token: str,
        mailbox: str,
        provider_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Extend the watch before it expires. Returns updated config."""

    @abstractmethod
    async def stop_watch(
        self,
        access_token: str,
        mailbox: str,
        provider_config: Dict[str, Any],
    ) -> None:
        """Tear down the watch and any provider-side resources it created."""

    # ---- Push handling ---------------------------------------------------

    def verify_push(
        self,
        authorization_header: Optional[str],
        expected_audience: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Authenticate a push request. Raises `PushSignatureError` if it cannot
        be attributed to the provider. Providers that do not sign pushes leave
        this as a no-op."""
        return {}

    def extract_push_cursor(self, raw_push_payload: Dict[str, Any]) -> Optional[int]:
        """The provider's monotonically increasing cursor (Gmail: historyId), so
        a receiver can drop stale redeliveries before doing any real work.

        None when it cannot be derived; the caller should then proceed normally.
        """
        return None

    @abstractmethod
    async def fetch_events(
        self,
        access_token: str,
        provider_config: Dict[str, Any],
        raw_push_payload: Dict[str, Any],
    ) -> List[NormalizedEmail]:
        """Decode a push payload and return the messages it refers to."""
