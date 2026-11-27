"""Plain data the rate-limit layer passes around."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Classification:
    """What a provider failure is, and how long the provider asked to wait."""

    kind: str  # 'rate_limit' | 'transient' | 'fatal'
    status: Optional[int] = None
    retry_after: Optional[float] = None


@dataclass(frozen=True)
class RateLimitScope:
    """The calls that share one gate: one quota on one provider's model."""

    provider: str
    model: str
    # A proxy and the direct API have separate limits.
    base_url: str = ''
    # Vertex location or Bedrock region, where quotas are regional.
    region: str = ''
    # Hash of the API key, or the Vertex project.
    account: str = ''
