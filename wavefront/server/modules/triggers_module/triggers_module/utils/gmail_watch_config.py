from mailer import GmailWatchConfig


class GmailWatchConfigError(Exception):
    """Raised when inbox-watch Pub/Sub settings are missing or incomplete."""


def build_gmail_watch_config(
    pubsub_project_id: str,
    push_endpoint_template: str,
    pubsub_topic_prefix: str = 'agentic-trigger',
    oidc_service_account_email: str | None = None,
) -> GmailWatchConfig:
    """Build watch config from triggers runtime settings only.

    No env/config.ini dual paths and no soft defaults beyond the topic prefix.
    Callers (DI) must supply the required fields.
    """
    project_id = (pubsub_project_id or '').strip()
    push_endpoint = (push_endpoint_template or '').strip()
    topic_prefix = (pubsub_topic_prefix or '').strip() or 'agentic-trigger'
    oidc_sa = (oidc_service_account_email or '').strip() or None

    missing = []
    if not project_id:
        missing.append('triggers_gmail.pubsub_project_id')
    if not push_endpoint:
        missing.append('triggers_gmail.push_endpoint_template')
    if missing:
        raise GmailWatchConfigError(
            'Gmail inbox watch is not configured: missing ' + ', '.join(missing)
        )

    return GmailWatchConfig(
        pubsub_project_id=project_id,
        push_endpoint_template=push_endpoint,
        pubsub_topic_prefix=topic_prefix,
        oidc_service_account_email=oidc_sa,
    )
