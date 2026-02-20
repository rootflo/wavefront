"""Language validation utilities for voice agents"""

from typing import List, Dict, Set, Optional, Tuple

# Language code to human-readable name mapping
LANGUAGE_NAMES: Dict[str, str] = {
    'ar': 'Arabic',
    'bg': 'Bulgarian',
    'bn': 'Bengali',
    'cs': 'Czech',
    'da': 'Danish',
    'de': 'German',
    'el': 'Greek',
    'en': 'English',
    'es': 'Spanish',
    'fi': 'Finnish',
    'fil': 'Filipino',
    'fr': 'French',
    'gu': 'Gujarati',
    'he': 'Hebrew',
    'hi': 'Hindi',
    'hr': 'Croatian',
    'hu': 'Hungarian',
    'id': 'Indonesian',
    'it': 'Italian',
    'ja': 'Japanese',
    'ka': 'Georgian',
    'kn': 'Kannada',
    'ko': 'Korean',
    'ml': 'Malayalam',
    'mr': 'Marathi',
    'ms': 'Malay',
    'nl': 'Dutch',
    'no': 'Norwegian',
    'pa': 'Punjabi',
    'pl': 'Polish',
    'pt': 'Portuguese',
    'ro': 'Romanian',
    'ru': 'Russian',
    'sk': 'Slovak',
    'sv': 'Swedish',
    'ta': 'Tamil',
    'te': 'Telugu',
    'th': 'Thai',
    'tl': 'Tagalog',
    'tr': 'Turkish',
    'uk': 'Ukrainian',
    'vi': 'Vietnamese',
    'zh': 'Chinese',
}

# Provider language support (extracted from pipecat language mappings)
ELEVENLABS_LANGUAGES: Set[str] = {
    'ar',
    'bg',
    'cs',
    'da',
    'de',
    'el',
    'en',
    'es',
    'fi',
    'fil',
    'fr',
    'gu',
    'hi',
    'hr',
    'hu',
    'id',
    'it',
    'ja',
    'kn',
    'ko',
    'ml',
    'ms',
    'nl',
    'no',
    'pl',
    'pt',
    'ro',
    'ru',
    'sk',
    'sv',
    'ta',
    'te',
    'tr',
    'uk',
    'vi',
    'zh',
}

CARTESIA_LANGUAGES: Set[str] = {
    'ar',
    'bg',
    'bn',
    'cs',
    'da',
    'de',
    'en',
    'el',
    'es',
    'fi',
    'fr',
    'gu',
    'he',
    'hi',
    'hr',
    'hu',
    'id',
    'it',
    'ja',
    'ka',
    'kn',
    'ko',
    'ml',
    'mr',
    'ms',
    'nl',
    'no',
    'pa',
    'pl',
    'pt',
    'ro',
    'ru',
    'sk',
    'sv',
    'ta',
    'te',
    'th',
    'tl',
    'tr',
    'uk',
    'vi',
    'zh',
}

# Deepgram STT supports 40+ languages
SARVAM_LANGUAGES: Set[str] = {
    'bn',
    'en',
    'gu',
    'hi',
    'kn',
    'ml',
    'mr',
    'or',
    'pa',
    'ta',
    'te',
}

DEEPGRAM_STT_LANGUAGES: Set[str] = {
    'ar',
    'bg',
    'ca',
    'cs',
    'da',
    'de',
    'el',
    'en',
    'es',
    'et',
    'fi',
    'fr',
    'hi',
    'hu',
    'id',
    'it',
    'ja',
    'ko',
    'lt',
    'lv',
    'ms',
    'nl',
    'no',
    'pl',
    'pt',
    'ro',
    'ru',
    'sk',
    'sv',
    'ta',
    'te',
    'th',
    'tr',
    'uk',
    'vi',
    'zh',
}


def get_tts_supported_languages(provider: str) -> Set[str]:
    """
    Get supported languages for a TTS provider.

    Args:
        provider: TTS provider name (elevenlabs, cartesia, deepgram, etc.)

    Returns:
        Set of supported language codes

    Raises:
        ValueError: If provider is unknown
    """
    provider = provider.lower()

    if provider == 'elevenlabs':
        return ELEVENLABS_LANGUAGES
    elif provider == 'cartesia':
        return CARTESIA_LANGUAGES
    elif provider == 'deepgram':
        # Deepgram TTS: language is implicit in voice_id, no explicit language param
        # Return empty set to indicate validation should be skipped
        return set()
    elif provider == 'sarvam':
        return SARVAM_LANGUAGES
    elif provider in ['azure', 'google', 'aws']:
        # For providers not yet fully implemented, skip validation
        return set()
    else:
        raise ValueError(f'Unknown TTS provider: {provider}')


def get_stt_supported_languages(provider: str) -> Set[str]:
    """
    Get supported languages for an STT provider.

    Args:
        provider: STT provider name (deepgram, assemblyai, whisper, etc.)

    Returns:
        Set of supported language codes

    Raises:
        ValueError: If provider is unknown
    """
    provider = provider.lower()

    if provider == 'deepgram':
        return DEEPGRAM_STT_LANGUAGES
    elif provider == 'sarvam':
        return SARVAM_LANGUAGES
    elif provider == 'elevenlabs':
        return ELEVENLABS_LANGUAGES
    elif provider in ['assemblyai', 'whisper', 'google', 'azure']:
        # For providers not yet fully implemented, skip validation
        return set()
    else:
        raise ValueError(f'Unknown STT provider: {provider}')


def validate_languages_for_configs(
    supported_languages: List[str], tts_provider: str, stt_provider: str
) -> Tuple[bool, Optional[str]]:
    """
    Validate that all supported languages are available in both TTS and STT providers.

    Args:
        supported_languages: List of language codes to validate
        tts_provider: TTS provider name
        stt_provider: STT provider name

    Returns:
        Tuple of (is_valid, error_message). error_message is None if valid.
    """
    if not supported_languages:
        return False, 'supported_languages cannot be empty'

    # Get provider capabilities
    try:
        tts_langs = get_tts_supported_languages(tts_provider)
        stt_langs = get_stt_supported_languages(stt_provider)
    except ValueError as e:
        return False, str(e)

    # Skip TTS validation if provider doesn't support explicit language param
    if not tts_langs:
        tts_langs = set(supported_languages)  # Assume all are valid

    # Skip STT validation if not implemented
    if not stt_langs:
        stt_langs = set(supported_languages)  # Assume all are valid

    # Validate each language
    unsupported_tts = []
    unsupported_stt = []

    for lang in supported_languages:
        if lang not in tts_langs:
            unsupported_tts.append(lang)
        if lang not in stt_langs:
            unsupported_stt.append(lang)

    if unsupported_tts or unsupported_stt:
        errors = []
        if unsupported_tts:
            errors.append(
                f"TTS provider '{tts_provider}' does not support: {', '.join(unsupported_tts)}"
            )
        if unsupported_stt:
            errors.append(
                f"STT provider '{stt_provider}' does not support: {', '.join(unsupported_stt)}"
            )
        return False, '; '.join(errors)

    return True, None


def validate_default_language(
    default_language: str, supported_languages: List[str]
) -> Tuple[bool, Optional[str]]:
    """
    Validate that default_language is in supported_languages.

    Args:
        default_language: Default language code
        supported_languages: List of supported language codes

    Returns:
        Tuple of (is_valid, error_message). error_message is None if valid.
    """
    if default_language not in supported_languages:
        return (
            False,
            f"default_language '{default_language}' must be in supported_languages",
        )
    return True, None


def get_language_names(language_codes: List[str]) -> List[str]:
    """
    Convert language codes to human-readable names.

    Args:
        language_codes: List of language codes (e.g., ['en', 'es', 'hi'])

    Returns:
        List of language names (e.g., ['English', 'Spanish', 'Hindi'])
    """
    return [LANGUAGE_NAMES.get(code, code) for code in language_codes]


def format_language_prompt(supported_languages: List[str]) -> str:
    """
    Format language list for welcome audio prompt.

    Args:
        supported_languages: List of language codes

    Returns:
        Formatted string for audio prompt (e.g., "English, Spanish, or Hindi")
    """
    names = get_language_names(supported_languages)

    if len(names) == 1:
        return names[0]
    elif len(names) == 2:
        return f'{names[0]} or {names[1]}'
    else:
        # Oxford comma style: "English, Spanish, or Hindi"
        return ', '.join(names[:-1]) + f', or {names[-1]}'
