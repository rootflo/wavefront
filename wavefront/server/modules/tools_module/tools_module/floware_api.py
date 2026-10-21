"""Connection settings for the tools that call floware's own REST API."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FlowareApiClient:
    """Where floware's API lives and how internal callers authenticate to it.

    Built once by ``ToolsContainer`` and bound as the first argument of every
    tool function that calls floware (see ``tools_module.registry``), so the
    functions carry no module-level state of their own.
    """

    base_url: str
    passthrough_secret: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, 'base_url', self.base_url.rstrip('/'))
        object.__setattr__(self, 'passthrough_secret', self.passthrough_secret or None)

    def headers(self) -> dict[str, str]:
        """JSON headers, plus the passthrough secret when one is configured.

        Same internal-call convention as the other cross-service callers: the
        passthrough secret outside production, service mesh identity within it.
        """
        headers = {'Content-Type': 'application/json'}
        if self.passthrough_secret:
            headers['X-Passthrough'] = self.passthrough_secret
        return headers
