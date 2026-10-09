"""Server-sent event plumbing shared by the streaming inference endpoints."""

import json
from typing import Any, Dict

#: Headers every SSE response needs. ``X-Accel-Buffering`` is the one that is
#: easy to miss: without it nginx buffers the response and the client receives
#: the whole stream at once, at the end, which looks exactly like streaming
#: never having been implemented.
SSE_HEADERS = {
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive',
    'Content-Type': 'text/event-stream',
    'Transfer-Encoding': 'chunked',
    'X-Accel-Buffering': 'no',
}


def format_sse(event: Dict[str, Any]) -> str:
    """Render one event as an SSE ``data:`` frame."""
    return f'data: {json.dumps(event)}\n\n'
