"""The action registry.

Actions are registered as routes declare them (``requires``) or by
``define_action`` for checks made inside a handler. The registry is the source
of the exported catalog.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from authz_module.legacy import LegacyRule

ACTION_NAME = re.compile(r'^[a-z][a-z0-9_]*:[A-Z][A-Za-z0-9]*$')


@dataclass(frozen=True)
class ActionSpec:
    name: str
    legacy: LegacyRule
    resource_type: str | None = None
    description: str = ''

    @property
    def service(self) -> str:
        return self.name.split(':', 1)[0]

    def to_dict(self) -> dict:
        return {
            'action': self.name,
            'service': self.service,
            'resource_type': self.resource_type,
            'description': self.description,
            'legacy': str(self.legacy),
        }


class ActionConflict(ValueError):
    pass


_registry: dict[str, ActionSpec] = {}


def define_action(
    name: str,
    *,
    legacy: LegacyRule,
    resource_type: str | None = None,
    description: str = '',
) -> ActionSpec:
    """Register an action, or return the existing one.

    Declaring the same action twice is how two routes share one permission, so
    it is allowed -- but only with the same legacy rule and resource type. A
    mismatch would make the default authorizer's answer depend on which route
    was hit, so it is an error.
    """
    if not ACTION_NAME.match(name):
        raise ValueError(
            f'Invalid action name {name!r}: expected <service>:<Verb><Noun>, '
            "e.g. 'agents:CreateAgent'"
        )
    existing = _registry.get(name)
    if existing is not None:
        if existing.legacy != legacy:
            raise ActionConflict(
                f'Action {name} declared with legacy rule {legacy}, '
                f'already declared with {existing.legacy}'
            )
        if (
            resource_type
            and existing.resource_type
            and resource_type != existing.resource_type
        ):
            raise ActionConflict(
                f'Action {name} declared on resource type {resource_type}, '
                f'already declared on {existing.resource_type}'
            )
        if (resource_type and not existing.resource_type) or (
            description and not existing.description
        ):
            existing = ActionSpec(
                name=name,
                legacy=legacy,
                resource_type=existing.resource_type or resource_type,
                description=existing.description or description,
            )
            _registry[name] = existing
        return existing
    spec = ActionSpec(
        name=name, legacy=legacy, resource_type=resource_type, description=description
    )
    _registry[name] = spec
    return spec


def get_action(name: str) -> ActionSpec:
    try:
        return _registry[name]
    except KeyError:
        raise KeyError(f'Unknown action {name!r}; declare it with define_action')


def all_actions() -> list[ActionSpec]:
    return sorted(_registry.values(), key=lambda spec: spec.name)
