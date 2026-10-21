"""Conversation events a session surfaces to its client.

The pipeline emits these from every flow. Telephony has no client to tell, so
it uses the no-op base; browser (WebRTC) sessions use ``ClientSessionMessenger``,
which sends them to the app over RTVI.
"""

STATE_LISTENING = 'listening'
STATE_THINKING = 'thinking'
STATE_SPEAKING = 'speaking'


class SessionEvents:
    async def emit_agent_state(self, state: str) -> None:
        pass

    async def emit_transcript(self, text: str) -> None:
        pass

    async def emit_language_changed(self, language: str) -> None:
        pass
