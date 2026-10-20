"""Move a live session's TTS/STT services to another language."""

from typing import Any, Dict, Tuple

from call_processing.services.common.providers.stt_service import STTServiceFactory
from call_processing.services.common.providers.tts_service import TTSServiceFactory


async def queue_language_update(
    task: Any,
    *,
    tts_provider: str,
    stt_provider: str,
    tts_voice_ids: Dict[str, str],
    language: str,
) -> Tuple[bool, bool]:
    """Queue the TTS (voice + language) and STT (language) settings updates.

    Returns whether the TTS and the STT frame were queued; a provider that cannot
    change language at runtime yields no frame.
    """
    tts_frame = TTSServiceFactory.create_language_update_frame(
        tts_provider, language, tts_voice_ids.get(language)
    )
    if tts_frame:
        await task.queue_frame(tts_frame)

    stt_frame = STTServiceFactory.create_language_update_frame(stt_provider, language)
    if stt_frame:
        await task.queue_frame(stt_frame)

    return bool(tts_frame), bool(stt_frame)
