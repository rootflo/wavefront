"""System-message text shared by the telephony and browser (WebRTC) flows.

Everything the LLM reads that is not written by the agent author lives here
(language rules, tool descriptions), so wording changes do not touch the
pipeline code. Telephony-only text is in ``services/telephony/prompts.py``.
"""

from typing import List

from call_processing.constants.language_config import LANGUAGE_INSTRUCTIONS


def language_instruction(language: str) -> str:
    """The 'Respond in <language>.' line prefixed to a multi-language prompt."""
    return LANGUAGE_INSTRUCTIONS.get(
        language, LANGUAGE_INSTRUCTIONS.get('en', 'Respond in English.')
    )


def language_switching_rules(
    supported_language_names: List[str], current_language_name: str
) -> str:
    """Rules telling the LLM when to call ``detect_and_switch_language``."""
    supported = ', '.join(supported_language_names)
    return (
        f'\n\nLANGUAGE SWITCHING RULES (follow exactly, no exceptions):\n'
        f'Supported languages: {supported}.\n'
        f'Current language: {current_language_name}.\n\n'
        f'CASE 1 — USER WANTS THE ASSISTANT TO USE A DIFFERENT LANGUAGE:\n'
        f'The user is asking or implying that they want the conversation to happen in a specific supported language. Triggers include:\n'
        f'  - Saying a supported language name alone (e.g. "Hindi", "English", "Tamil")\n'
        f'  - Asking if you can speak/use a language (e.g. "Can you speak in English?", "क्या आप हिंदी में बात कर सकते हैं?")\n'
        f'  - Requesting a switch (e.g. "switch to Hindi", "speak in Tamil", "Hindi mein baat karo", "change language")\n'
        f'  - Saying "speaking [language]" implying they want the assistant to speak it (e.g. "Speaking Hindi")\n'
        f'  - Responding with a language name after being asked which language they want\n'
        f'  - A word that phonetically resembles a supported language name — STT often mishears language names '
        f'(e.g. "Hindi" → "Indy" or "Indie", "Kannada" → "Canada", "Telugu" → "Tell you"). '
        f'Use phonetic judgment: if the word sounds like a supported language name in context, treat it as CASE 1.\n'
        f'BIAS RULE: When in doubt between CASE 1 and CASE 2, if a supported language name (or phonetic match) '
        f'appears in the message, default to CASE 1.\n'
        f'ACTION: Call detect_and_switch_language immediately. Do NOT ask for confirmation. Do NOT say anything before calling the tool.\n\n'
        f'CASE 2 — USER SPEAKS IN A DIFFERENT LANGUAGE (no language name mentioned, no switch request):\n'
        f'The user sends a full message in a language different from the current language, '
        f'with NO mention of a language name and NO request to switch. They are just talking.\n'
        f'NOTE: STT may transcribe foreign speech phonetically in the current language script — '
        f'e.g. if current language is English and the user speaks Hindi, STT may output romanized Hindi '
        f'like "Ha muje naye loan ke baare mai batao". Recognize this as Hindi input, not English.\n'
        f'ACTION: Do NOT call detect_and_switch_language. Do NOT answer their query. '
        f'Respond in the CURRENT language (the language you are currently configured to speak) with this meaning: '
        f'"Are you trying to switch the language? If yes, please say one of: {supported}"\n\n'
        f'CASE 3 — UNSUPPORTED LANGUAGE REQUESTED:\n'
        f'The user requests a language not in the supported list.\n'
        f'ACTION: Do NOT call detect_and_switch_language. Inform the user that only these languages are supported: '
        f'{supported}.\n\n'
        f'CRITICAL RULES:\n'
        f'- Never call detect_and_switch_language for Case 2 or Case 3.\n'
        f'- Never answer a query in the wrong language before switching.\n'
        f'- Never ask for confirmation before switching in Case 1.\n'
        f'- Never respond with your own words before or instead of calling the tool in Case 1.\n'
        f'- Never invent responses outside these three cases.'
    )


# ------------------------------------------------------------ detect_and_switch_language


def language_tool_description(
    supported_language_names: List[str], current_language: str
) -> str:
    return (
        f"Switch the conversation language. "
        f"Call this when the user wants the assistant to use a specific language — "
        f"this includes: saying a language name directly ('Hindi', 'Tamil'), "
        f"asking 'can you speak in X?', saying 'speaking [language]', "
        f"or phrases like 'switch to Hindi', 'speak in Tamil', 'Hindi mein baat karo'. "
        f"STT may mishear language names (e.g. 'Hindi' → 'Indy', 'Kannada' → 'Canada') — use phonetic judgment. "
        f"When in doubt and a language name is present, call this tool. "
        f"Do NOT call this tool when the user simply starts speaking in another language with no language name and no switch request — "
        f"in that case respond in the current language asking if they want to switch. "
        f"Only switch to supported languages: {', '.join(supported_language_names)}. "
        f"Current language: {current_language}."
    )


def language_tool_target_description(supported_languages: List[str]) -> str:
    return f"Target language code. Must be one of: {', '.join(supported_languages)}"


LANGUAGE_TOOL_INTENT_DESCRIPTION = (
    "The user's statement indicating language preference (for logging)"
)


def unsupported_language_error(
    target_language: str, supported_languages: List[str]
) -> str:
    """Tool result for a switch to a language the agent does not support."""
    return (
        f"'{target_language}' is not a supported language. "
        f"Tell the user you're sorry but this language is not supported, "
        f"and that you can only converse in: {', '.join(supported_languages)}. "
        f"Do not attempt any language switch."
    )


def direct_language_switch_note(language_name: str) -> str:
    """Added after a user message that only chose a language, once the service
    has switched to it without the tool (``direct_language_switch.py``)."""
    return (
        f'The user chose {language_name}, and the conversation language is now '
        f'{language_name}. Do not call detect_and_switch_language for this message: '
        f'the switch is done. Reply to the user in {language_name}.'
    )


# ---------------------------------------------------------------------- end_conversation

END_CONVERSATION_DESCRIPTION = (
    'End the call. Call this only when the user clearly wants to finish: '
    'a goodbye ("bye", "goodbye"), or "that\'s all" / "I\'m done" / "nothing else" '
    'after their request has been handled. A "thank you" or "okay" in the middle '
    'of the conversation is NOT a reason to end it; if unsure, ask whether there '
    'is anything else instead of ending.'
)

END_CONVERSATION_FAREWELL_DESCRIPTION = (
    'Optional custom farewell message to say to the user before ending. '
    'If not provided, a default farewell is used.'
)


# ---------------------------------------------------------------------- user_idle

USER_IDLE_CHECK_IN_PROMPT = (
    'The user has not said anything for a while. In one short sentence, in the '
    'language of the conversation, politely ask whether they are still there. '
    'If you were waiting on an answer to a question, you may briefly restate it. '
    'Do not call any tools.'
)

USER_IDLE_GOODBYE_PROMPT = (
    'The user has not answered your check-ins. In one short sentence, in the '
    'language of the conversation, say that you will end the call now since they '
    'seem to be away, and say goodbye. Do not ask anything and do not call any tools.'
)
