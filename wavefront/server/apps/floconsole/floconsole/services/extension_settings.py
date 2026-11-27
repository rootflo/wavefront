"""The console's remote UI extensions setting ([extensions] remotes)."""

import json
from typing import Any

from common_module.log.logger import logger

REMOTE_TYPES = ('module', 'var')


def parse_extensions(raw: str | None) -> list[dict[str, Any]]:
    """The configured remotes, keeping only well-formed entries.

    A malformed setting must not break the console: it is logged and the
    console runs with the remotes that are valid (or none).
    """
    if not raw or not raw.strip():
        return []
    try:
        entries = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error(f'[extensions] remotes is not valid JSON; loading none: {exc}')
        return []
    if not isinstance(entries, list):
        logger.error('[extensions] remotes must be a JSON list; loading none')
        return []

    remotes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in entries:
        name = entry.get('name') if isinstance(entry, dict) else None
        url = entry.get('entry') if isinstance(entry, dict) else None
        remote_type = entry.get('type', 'module') if isinstance(entry, dict) else None
        if not isinstance(name, str) or not name or not isinstance(url, str) or not url:
            logger.error(f'[extensions] skipping malformed remote {entry!r}')
            continue
        if remote_type not in REMOTE_TYPES:
            logger.error(f'[extensions] skipping {name}: unknown type {remote_type!r}')
            continue
        if name in seen:
            logger.error(f'[extensions] skipping duplicate remote {name}')
            continue
        seen.add(name)
        remotes.append({'name': name, 'entry': url, 'type': remote_type})
    return remotes
