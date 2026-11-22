"""Checking in on a silent caller, and hanging up if they never answer.

Configured with the ``idle_*`` keys in ``conversation_config.turn_taking``
(see ``turn_taking.py``).

The silence is timed by Pipecat's user idle controller: it starts when the bot
stops speaking and is cancelled by anyone speaking or a tool call starting, so
the check-in (bot speech itself) re-arms it. Each expiry asks the LLM to check
in, in the conversation's language. One more after ``idle_max_check_ins`` says
goodbye and ends the call: by default the LLM words the goodbye too and the
call ends once it has been spoken; with ``idle_fixed_goodbye`` the
``idle_goodbye_message`` is spoken as written instead.

Only transcribed words count as an answer: a cough or line noise restarts the
timer but not the count, so a call with nobody on it always ends.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

DEFAULT_IDLE_GOODBYE = (
    "It seems you're no longer there, so I'll end the call now. Goodbye!"
)

# How long the LLM gets to produce and speak the goodbye before the call is
# ended without it (e.g. the LLM errored and said nothing)
IDLE_GOODBYE_GRACE_SECS = 20.0
# Goodbyes asked for before hanging up without one: line noise can cut every
# goodbye off, and must not keep an empty call open
MAX_IDLE_GOODBYES = 2


class IdleAction(str, Enum):
    CHECK_IN = 'check_in'
    # Ask the LLM for a goodbye; the call ends once it has been spoken
    SAY_GOODBYE = 'say_goodbye'
    # Speak the configured goodbye, then end the call
    FIXED_GOODBYE = 'fixed_goodbye'
    # A goodbye was asked for but never finished; end without another one
    HANG_UP = 'hang_up'


class IdleCheckIns:
    """Counts check-ins since the caller last said something transcribable."""

    def __init__(self, max_check_ins: int, *, fixed_goodbye: bool = False):
        self._max_check_ins = max_check_ins
        self._fixed_goodbye = fixed_goodbye
        self._count = 0
        self._goodbye_pending = False
        self._goodbyes_asked = 0
        # Tells a stale grace timer from the one for the current goodbye
        self._goodbye_id = 0
        self._ended = False

    @property
    def goodbye_id(self) -> int:
        return self._goodbye_id

    def user_spoke(self, transcript: Optional[str]) -> None:
        # Noise with no transcript is not an answer
        if self._ended or not (transcript and transcript.strip()):
            return
        self._count = 0
        self._goodbye_pending = False
        self._goodbyes_asked = 0

    def on_idle(self) -> Optional[IdleAction]:
        """What to do now the caller has been silent; None once the call is ending."""
        if self._ended:
            return None
        if self._count < self._max_check_ins:
            self._count += 1
            return IdleAction.CHECK_IN
        if self._fixed_goodbye:
            self._ended = True
            return IdleAction.FIXED_GOODBYE
        if self._goodbye_pending or self._goodbyes_asked >= MAX_IDLE_GOODBYES:
            self._ended = True
            return IdleAction.HANG_UP
        self._goodbye_pending = True
        self._goodbyes_asked += 1
        self._goodbye_id += 1
        return IdleAction.SAY_GOODBYE

    def assistant_turn_stopped(self, *, interrupted: bool, spoke: bool = True) -> bool:
        """True when this turn was the goodbye, spoken in full: end the call now.

        An interrupted goodbye is called off; the next silence asks for another,
        up to ``MAX_IDLE_GOODBYES``, then hangs up without one. A turn that said
        nothing (e.g. only a tool call) is not the goodbye, which stays pending.
        """
        if self._ended or not self._goodbye_pending:
            return False
        if not spoke and not interrupted:
            return False
        self._goodbye_pending = False
        if interrupted:
            return False
        self._ended = True
        return True

    def goodbye_overdue(self, goodbye_id: int) -> bool:
        """True when goodbye ``goodbye_id`` was never spoken: end the call anyway."""
        if self._ended or not self._goodbye_pending or goodbye_id != self._goodbye_id:
            return False
        self._ended = True
        return True
