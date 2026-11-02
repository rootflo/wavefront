"""Move a live session's TTS/STT services to another language."""

from typing import Any, Dict, Optional, Tuple

from pipecat.frames.frames import STTUpdateSettingsFrame, TTSUpdateSettingsFrame

from call_processing.services.common.prompts import language_instruction
from call_processing.services.common.providers.stt_service import STTServiceFactory
from call_processing.services.common.providers.tts_service import TTSServiceFactory


def language_update_frames(
    *,
    tts_provider: str,
    stt_provider: str,
    tts_voice_ids: Dict[str, str],
    language: str,
) -> Tuple[Optional[TTSUpdateSettingsFrame], Optional[STTUpdateSettingsFrame]]:
    """The TTS (voice + language) and STT (language) settings updates; a provider
    that cannot change language at runtime yields no frame."""
    tts_frame = TTSServiceFactory.create_language_update_frame(
        tts_provider, language, tts_voice_ids.get(language)
    )
    stt_frame = STTServiceFactory.create_language_update_frame(stt_provider, language)
    return tts_frame, stt_frame


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
    tts_frame, stt_frame = language_update_frames(
        tts_provider=tts_provider,
        stt_provider=stt_provider,
        tts_voice_ids=tts_voice_ids,
        language=language,
    )
    if tts_frame:
        await task.queue_frame(tts_frame)
    if stt_frame:
        await task.queue_frame(stt_frame)

    return bool(tts_frame), bool(stt_frame)


def set_prompt_language(
    context: Any, language_state: Dict[str, Any], language: str
) -> bool:
    """Point the system prompt at ``language``; False without a stored base prompt.

    Mutates the system message in place so the conversation history (including
    a tool call and result being appended by Pipecat) is kept.
    """
    base_prompt = language_state.get('original_system_prompt')
    if not base_prompt:
        return False
    messages = context.get_messages()
    messages[0] = {
        'role': 'system',
        'content': f'{language_instruction(language)}\n\n{base_prompt}',
    }
    context.set_messages(messages)
    return True
