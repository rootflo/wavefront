from typing import Optional
from urllib.parse import urlsplit, urlunsplit


def normalize_asset_url(asset_url: Optional[str]) -> Optional[str]:
    """Validate a configured asset base URL; None or blank means unset."""
    if asset_url is None or not asset_url.strip():
        return None
    value = asset_url.strip().rstrip('/')
    parts = urlsplit(value)
    if (
        parts.scheme not in ('http', 'https')
        or not parts.hostname
        or parts.query
        or parts.fragment
    ):
        raise ValueError(
            'asset_url must be an http(s) URL with a host and no query or '
            f'fragment, got {asset_url!r}'
        )
    return value


def rebase_url(url: str, asset_url: Optional[str]) -> str:
    """Swap ``url``'s scheme and host for ``asset_url``'s (its path is prefixed); query kept."""
    if not asset_url:
        return url
    base = urlsplit(asset_url)
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
