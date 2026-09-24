from dataclasses import dataclass


@dataclass(frozen=True)
class KmsKeySettings:
    provider: str
    key: str  # GCP crypto key | AWS key ARN | Azure key name
    key_version: str | None = None
    key_ring: str | None = None  # gcp
    project_id: str | None = None  # gcp
    location: str | None = None  # gcp
    region: str | None = None  # aws
    vault_url: str | None = None  # azure
    client_id: str | None = None
    client_secret: str | None = None
    tenant_id: str | None = None


@dataclass(frozen=True)
class QueueSettings:
    provider: str
    target: str  # topic id | queue url | queue name
    subscription: str | None = None  # consumers only
    project_id: str | None = None
    account_url: str | None = None
