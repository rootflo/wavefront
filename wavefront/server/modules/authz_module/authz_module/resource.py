"""What an action is performed on."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Callable, Mapping

from starlette.requests import HTTPConnection


@dataclass(frozen=True)
class ResourceRef:
    """A resource by type and id. ``id`` is None for a collection (list, create)."""

    type: str
    id: str | None = None
    attributes: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))

    def __str__(self) -> str:
        return self.type if self.id is None else f'{self.type}/{self.id}'


ResourceResolver = Callable[[HTTPConnection], ResourceRef]


def from_path(resource_type: str, param: str | None = None) -> ResourceResolver:
    """Resolve the resource from a path parameter.

    ``from_path('agent', 'agent_id')`` gives ``ResourceRef('agent', <agent_id>)``;
    with no ``param`` it names the collection.
    """

    def resolve(conn: HTTPConnection) -> ResourceRef:
        if param is None:
            return ResourceRef(resource_type)
        value = conn.path_params.get(param)
        return ResourceRef(resource_type, None if value is None else str(value))

    resolve.resource_type = resource_type  # type: ignore[attr-defined]
    return resolve


def resource_type_of(resolver: ResourceResolver | ResourceRef | None) -> str | None:
    if resolver is None:
        return None
    if isinstance(resolver, ResourceRef):
        return resolver.type
    return getattr(resolver, 'resource_type', None)
