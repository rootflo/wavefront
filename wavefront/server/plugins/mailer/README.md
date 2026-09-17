# Mailer plugin

Provider implementations for connected mailboxes: OAuth consent and token
exchange, sending, reading, and inbox watch subscriptions.

The package is called `mailer` rather than `email` because a top-level `email`
package would shadow the standard library `email` module that the MIME builders
in `helper.py` import.

## Layout

| Path | Purpose |
| --- | --- |
| `types.py` | `EmailProviderABC`, `EmailProviderType`, `EmailCapability`, and the data carried across the interface |
| `helper.py` | MIME assembly and scope resolution shared by all providers |
| `factory.py` | `EmailProviderFactory` — validates config and caches provider instances per OAuth app |
| `gmail/` | Gmail API provider: OAuth, `messages.send`, history fetch, `users.watch` (Pub/Sub config passed in by triggers) |
| `outlook/` | Microsoft Graph provider: delegated OAuth, `sendMail`, message fetch |

## Capabilities

Callers ask for capabilities, not raw scopes. Each provider maps them to its own
scope strings:

| Capability | Gmail | Outlook |
| --- | --- | --- |
| `read` | `gmail.readonly` | `Mail.Read` |
| `send` | `gmail.send` | `Mail.Send` |
| `modify` | `gmail.modify` | `Mail.ReadWrite` |

Identity scopes needed to resolve the connected mailbox address are always
included.

## Usage

```python
from mailer import EmailCapability, EmailProviderType, get_email_provider_factory
from mailer.gmail import GmailAppConfig

factory = get_email_provider_factory()
provider = factory.get_provider(app_id, EmailProviderType.GMAIL, config_dict)

url = provider.build_consent_url(
    state=state,
    scopes=provider.scopes_for([EmailCapability.READ, EmailCapability.SEND]),
)
```

Provider instances are cached by OAuth app id. Call `update_provider` when an
app's configuration changes and `remove_provider` when it is deleted, so the
cache does not serve stale credentials.
