"""Load an app's config.ini once, strictly.

Defaults live in the ini (``${VAR:default}``). A variable with no default is
required: ``envs_required`` fails at startup when it is unset, instead of
becoming an empty string that breaks later.
"""

from __future__ import annotations

from pathlib import Path

from dependency_injector.providers import Configuration

_TRUTHY = frozenset({'1', 'true', 'yes', 'on'})


def load_ini(config: Configuration, path: str | Path) -> None:
    """Load ``path`` into ``config``. The file must exist; unset required env vars raise."""
    config.from_ini(str(path), required=True, envs_required=True)


def is_truthy(value: object) -> bool:
    """config.ini booleans are strings. Empty or anything outside the truthy set is false."""
    return str(value or '').strip().lower() in _TRUTHY
