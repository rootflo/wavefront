"""Secret keys inside a telephony config's `credentials`, by provider.

These are encrypted at rest (when envelope encryption is on) and masked in API
responses. The other keys (`account_sid`, `subdomain`) stay readable.

call_processing keeps a copy of this map in
`call_processing/services/common/voice_agent_cache_service.py`; keep them in sync.
"""

from typing import Optional, Tuple

TELEPHONY_SECRET_FIELDS: dict[str, Tuple[str, ...]] = {
    'twilio': ('auth_token',),
    'exotel': ('api_key', 'api_token'),
    'smartflo': ('api_key',),
}


def telephony_secret_fields(provider: Optional[str]) -> Tuple[str, ...]:
    return TELEPHONY_SECRET_FIELDS.get(provider or '', ())
