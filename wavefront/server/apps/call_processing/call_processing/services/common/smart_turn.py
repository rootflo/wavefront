"""Smart Turn v3 analyzer that shares one ONNX model across calls.

``LocalSmartTurnAnalyzerV3`` builds a fresh ``InferenceSession`` in its
constructor. That runs on the event loop for every call and every agent swap,
stalling audio for every other live call while the model loads. The session
holds no per-stream state (the audio buffer lives on the analyzer) and
``InferenceSession.run`` is thread-safe, so one session serves every call.
"""

from __future__ import annotations

import threading
from typing import Any, Optional

from pipecat.audio.turn.smart_turn.base_smart_turn import BaseSmartTurn
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3

_session: Optional[Any] = None
_session_lock = threading.Lock()


def _shared_session() -> Any:
    global _session
    with _session_lock:
        if _session is None:
            # Built the way Pipecat builds it (bundled model, 1 inference thread)
            _session = LocalSmartTurnAnalyzerV3()._session
        return _session


def warm_up() -> None:
    """Load the model now (at startup) so the first call does not pay for it."""
    _shared_session()


class SharedSmartTurnAnalyzer(LocalSmartTurnAnalyzerV3):
    def __init__(self, **kwargs):
        # Skip LocalSmartTurnAnalyzerV3.__init__: it would load another session
        BaseSmartTurn.__init__(self, **kwargs)
        self._log_data = False
        self._session = _shared_session()
