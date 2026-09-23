import hashlib
from typing import Any

from common_module.common_cache import CommonCache

DEFAULT_COOLDOWN_SECONDS = 60
DEFAULT_MAX_PER_EMAIL = 3
DEFAULT_RATE_WINDOW_SECONDS = 3600


def _auth_setting(config: Any, key: str, default: int) -> int:
    auth = {}
    if config is not None:
        getter = getattr(config, 'get', None)
        auth = getter('auth') if callable(getter) else None
        if auth is None:
            try:
                auth = config['auth']
            except Exception:
                auth = {}
    if auth is None:
        auth = {}
    raw = auth.get(key, default) if hasattr(auth, 'get') else default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _email_digest(email: str) -> str:
    return hashlib.sha256(email.lower().strip().encode('utf-8')).hexdigest()[:32]


def password_reset_cooldown_seconds(config: Any) -> int:
    """Configured cooldown, normalized the same way rate limiting applies it."""
    return _auth_setting(
        config, 'password_reset_cooldown_seconds', DEFAULT_COOLDOWN_SECONDS
    )


def password_reset_rate_limited(cache: CommonCache, config: Any, email: str) -> bool:
    """True when this address is still in cooldown or has hit the hourly cap.

    Per-address only: volumetric and per-IP limiting is handled at the load
    balancer. The address is hashed so it never lands in a Redis key.
    """
    digest = _email_digest(email)
    cooldown = password_reset_cooldown_seconds(config)
    max_per_email = _auth_setting(
        config, 'password_reset_max_per_email', DEFAULT_MAX_PER_EMAIL
    )
    window = _auth_setting(
        config, 'password_reset_rate_window_seconds', DEFAULT_RATE_WINDOW_SECONDS
    )

    # Cooldown first: one mail per address per minute, using the same nx-lock
    # idiom as the export limit in datasource_controller. A caller already in
    # the cooldown never reaches the counter, so a request that was refused
    # does not eat into the hourly budget.
    if not cache.add(f'pwreset_cooldown_{digest}', '1', expiry=cooldown, nx=True):
        return True
    return cache.incr_with_expiry(f'pwreset_count_{digest}', window) > max_per_email
