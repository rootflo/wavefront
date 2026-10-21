"""Load an app's config.ini once, strictly.

Defaults live in the ini (``${VAR:default}``). A variable with no default is
required: loading fails at startup when it is unset, instead of becoming an
empty string that breaks later.
"""

from __future__ import annotations

import configparser
import os
import re
from pathlib import Path

from dependency_injector.providers import Configuration

_TRUTHY = frozenset({'1', 'true', 'yes', 'on'})

# Same marker syntax as dependency_injector's from_ini.
_ENV_MARKER = re.compile(r'\${(?P<name>[^}^{:]+)(?P<separator>:?)(?P<default>.*?)}')


def _resolve_env_markers(text: str) -> str:
    def substitute(match: re.Match) -> str:
        value = os.getenv(match.group('name'))
        if value is None:
            if match.group('separator') != ':':
                raise ValueError(
                    f'Missing required environment variable "{match.group("name")}"'
                )
            value = match.group('default')
        return value

    return _ENV_MARKER.sub(substitute, text)


def load_ini(config: Configuration, path: str | Path) -> None:
    """Load ``path`` into ``config``. The file must exist; unset required env vars raise.

    Not ``Configuration.from_ini``: it parses with ConfigParser's default
    interpolation, so an env value containing ``%`` (a URL-encoded password,
    e.g. ``%3D``) fails with InterpolationSyntaxError. Values are taken literally here.
    """
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(_resolve_env_markers(Path(path).read_text()))
    config.from_dict(
        {section: dict(parser.items(section)) for section in parser.sections()}
    )


def is_truthy(value: object) -> bool:
    """config.ini booleans are strings. Empty or anything outside the truthy set is false."""
    return str(value or '').strip().lower() in _TRUTHY
