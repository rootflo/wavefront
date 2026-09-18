from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GmailAppConfig:
    """Google OAuth application credentials only.

    Inbox watch / Pub/Sub settings are not part of an OAuth app — they belong to
    the triggers runtime and are passed separately as `GmailWatchConfig`.
    """

    client_id: str
    client_secret: str
    redirect_uri: str

    @staticmethod
    def required_fields() -> list[str]:
        return ['client_id', 'client_secret', 'redirect_uri']


@dataclass
class GmailWatchConfig:
    """Platform Pub/Sub plumbing for Gmail `users.watch`.

    Owned by triggers, not by the email OAuth app. Sending and OAuth work
    without any of these fields.
    """

    pubsub_project_id: str
    push_endpoint_template: str
    pubsub_topic_prefix: str = field(default='agentic-trigger')
    oidc_service_account_email: Optional[str] = None

    @staticmethod
    def required_fields() -> list[str]:
        return [
            'pubsub_project_id',
            'push_endpoint_template',
            'oidc_service_account_email',
        ]

    def push_endpoint(self, params: dict[str, str]) -> str:
        return self.push_endpoint_template.format(**params)

    def topic_path(self, watch_key: str) -> str:
        topic_name = f'{self.pubsub_topic_prefix}-{watch_key}'
        return f'projects/{self.pubsub_project_id}/topics/{topic_name}'

    def subscription_path(self, watch_key: str) -> str:
        sub_name = f'{self.pubsub_topic_prefix}-sub-{watch_key}'
        return f'projects/{self.pubsub_project_id}/subscriptions/{sub_name}'
