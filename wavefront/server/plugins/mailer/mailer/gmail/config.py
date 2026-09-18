from dataclasses import dataclass, field


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
    without any of these fields. OIDC service account is required so every
    registered watch stores an `oidc_audience` the push receiver can verify.
    """

    pubsub_project_id: str
    push_endpoint_template: str
    oidc_service_account_email: str
    pubsub_topic_prefix: str = field(default='agentic-trigger')

    def __post_init__(self) -> None:
        self.pubsub_project_id = (self.pubsub_project_id or '').strip()
        self.push_endpoint_template = (self.push_endpoint_template or '').strip()
        self.oidc_service_account_email = (
            self.oidc_service_account_email or ''
        ).strip()
        self.pubsub_topic_prefix = (
            self.pubsub_topic_prefix or ''
        ).strip() or 'agentic-trigger'
        missing = [
            name
            for name, value in (
                ('pubsub_project_id', self.pubsub_project_id),
                ('push_endpoint_template', self.push_endpoint_template),
                ('oidc_service_account_email', self.oidc_service_account_email),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                'GmailWatchConfig missing required fields: ' + ', '.join(missing)
            )

    @staticmethod
    def required_fields() -> list[str]:
        return [
            'pubsub_project_id',
            'push_endpoint_template',
            'oidc_service_account_email',
        ]

    def push_endpoint(self, params: dict[str, str]) -> str:
        """Fill the push URL template, or return a static proxy URL as-is.

        Direct receiver templates that target
        `/v1/triggers/{trigger_id}/{agentic_id}/invoke` must include both
        placeholders so Pub/Sub cannot be pointed at a malformed path.
        Templates without that invoke path (static proxies) are returned
        unchanged aside from optional formatting of any other fields.
        """
        template = self.push_endpoint_template
        if self._is_direct_trigger_invoke_template(template):
            missing = [
                name
                for name in ('trigger_id', 'agentic_id')
                if '{' + name + '}' not in template
            ]
            if missing:
                raise ValueError(
                    'push_endpoint_template for the direct trigger invoke path '
                    'must include placeholders: '
                    + ', '.join('{' + name + '}' for name in missing)
                )
            return template.format(**params)
        if '{' in template and '}' in template:
            return template.format(**params)
        return template

    def _is_direct_trigger_invoke_template(self, template: str) -> bool:
        """True when the template targets the Floware trigger push receiver path."""
        # Match the invoke route shape without requiring a specific host/prefix.
        return '/v1/triggers/' in template and template.rstrip('/').endswith('/invoke')

    def topic_path(self, watch_key: str) -> str:
        topic_name = f'{self.pubsub_topic_prefix}-{watch_key}'
        return f'projects/{self.pubsub_project_id}/topics/{topic_name}'

    def subscription_path(self, watch_key: str) -> str:
        sub_name = f'{self.pubsub_topic_prefix}-sub-{watch_key}'
        return f'projects/{self.pubsub_project_id}/subscriptions/{sub_name}'
