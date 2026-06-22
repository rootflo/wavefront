from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class TokenBundle:
    refresh_token: str
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
class NormalizedEmailEvent:
    provider_event_id: str
    subject: str
    sender: Optional[str]
    body_text: str
    attachments: List[Attachment] = field(default_factory=list)


class TriggerProvider(ABC):
    """Strategy interface for an external event source that can fire an agentic
    inference. Implementations cover the lifecycle: OAuth (optional), webhook
    subscription (start/renew/stop), and event normalisation."""

    provider_type: str = ''
    requires_oauth: bool = False

    def build_consent_url(self, trigger_id: str, scopes: List[str]) -> Optional[str]:
        if not self.requires_oauth:
            return None
        raise NotImplementedError

    async def exchange_oauth_code(self, code: str, trigger_id: str) -> TokenBundle:
        raise NotImplementedError

    async def refresh_access_token(self, refresh_token: str) -> TokenBundle:
        raise NotImplementedError

    @abstractmethod
    async def start_subscription(
        self,
        trigger_id: str,
        access_token: str,
        external_account_id: str,
        agentic_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Register the upstream subscription/watch. Returns provider_config to persist.

        `agentic_id` is the target entity (agent/workflow) id; some providers
        bake it into the push endpoint URL when registering the subscription.
        """

    @abstractmethod
    async def stop_subscription(
        self,
        provider_config: Dict[str, Any],
        access_token: str,
        external_account_id: str,
    ) -> None:
        """Tear down the upstream subscription/watch."""

    @abstractmethod
    async def renew_subscription(
        self,
        provider_config: Dict[str, Any],
        access_token: str,
        external_account_id: str,
    ) -> Dict[str, Any]:
        """Renew the upstream subscription/watch. Returns updated provider_config."""

    @abstractmethod
    async def fetch_events(
        self,
        access_token: str,
        provider_config: Dict[str, Any],
        raw_push_payload: Dict[str, Any],
    ) -> List[NormalizedEmailEvent]:
        """Decode the push payload, fetch the underlying messages, normalize."""

    def extract_push_cursor(self, raw_push_payload: Dict[str, Any]) -> Optional[int]:
        """Return the provider's monotonically-increasing cursor from a push
        payload (Gmail: historyId). Used by the webhook receiver to short-circuit
        stale redeliveries before doing any DB / upstream-API work.

        Return None if the cursor can't be derived; the receiver will then fall
        through to enqueueing normally.
        """
        return None
