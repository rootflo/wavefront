"""Selecting the provider: ``AUTHZ_PROVIDER`` names an entry point.

Entry points live in the ``wavefront.authz`` group. Each is a factory::

    def factory(*, service: str, default: AuthzProvider) -> AuthzProvider

``default`` is the service's built-in provider, so a factory can reuse its
authenticator and replace only the authorizer.
"""

from __future__ import annotations

import os
from importlib.metadata import entry_points

from authz_module.provider import AuthzProvider

ENTRY_POINT_GROUP = 'wavefront.authz'
ENV_VAR = 'AUTHZ_PROVIDER'
DEFAULT = 'default'


class ProviderNotFound(RuntimeError):
    pass


def selected_provider_name(name: str | None = None) -> str:
    return (name or os.environ.get(ENV_VAR) or DEFAULT).strip()


def load_provider(
    *, service: str, default: AuthzProvider, name: str | None = None
) -> AuthzProvider:
    """The provider ``name`` (default: ``$AUTHZ_PROVIDER``) for ``service``.

    An unknown name raises rather than falling back to the default: a typo must
    not silently run a service with weaker rules than intended.
    """
    selected = selected_provider_name(name)
    if selected == DEFAULT:
        return default

    matches = [
        ep for ep in entry_points(group=ENTRY_POINT_GROUP) if ep.name == selected
    ]
    if not matches:
        available = sorted(ep.name for ep in entry_points(group=ENTRY_POINT_GROUP))
        raise ProviderNotFound(
            f'{ENV_VAR}={selected!r} but no {ENTRY_POINT_GROUP!r} entry point has '
            f'that name (installed: {available or "none"})'
        )
    factory = matches[0].load()
    provider = factory(service=service, default=default)
    if not isinstance(provider, AuthzProvider):
        raise TypeError(
            f'Provider {selected!r} returned {type(provider).__name__}, '
            'expected AuthzProvider'
        )
    return provider
