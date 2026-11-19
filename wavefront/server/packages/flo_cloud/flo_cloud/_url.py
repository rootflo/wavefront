from typing import Optional
from urllib.parse import urlsplit, urlunsplit


def normalize_public_url(public_url: Optional[str]) -> Optional[str]:
    """Validate a configured public base URL; None or blank means unset."""
    if public_url is None or not public_url.strip():
        return None
    value = public_url.strip().rstrip('/')
    parts = urlsplit(value)
    if (
        parts.scheme not in ('http', 'https')
        or not parts.netloc
        or parts.query
        or parts.fragment
    ):
        raise ValueError(
            'public_url must be an http(s) URL with a host and no query or '
            f'fragment, got {public_url!r}'
        )
    return value


def rebase_url(url: str, public_url: Optional[str]) -> str:
    """Swap ``url``'s scheme and host for ``public_url``'s (its path is prefixed); query kept."""
    if not public_url:
        return url
    base = urlsplit(public_url)
    parts = urlsplit(url)
    return urlunsplit(
        (
            base.scheme,
            base.netloc,
            base.path.rstrip('/') + parts.path,
            parts.query,
            parts.fragment,
        )
    )
