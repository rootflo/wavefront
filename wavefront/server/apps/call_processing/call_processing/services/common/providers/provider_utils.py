"""Helpers shared by the LLM, STT and TTS provider factories."""

from typing import Any, Dict, Iterable, Mapping, Optional, TypeVar

from pipecat.transcriptions.language import Language

from call_processing.log.logger import logger

T = TypeVar('T')

# Short language codes stored on agents, mapped to what each provider expects
SARVAM_LANGUAGES = {
    'bn': Language.BN_IN,
    'en': Language.EN_IN,
    'gu': Language.GU_IN,
    'hi': Language.HI_IN,
    'kn': Language.KN_IN,
    'ml': Language.ML_IN,
    'mr': Language.MR_IN,
    'or': Language.OR_IN,
    'pa': Language.PA_IN,
    'ta': Language.TA_IN,
    'te': Language.TE_IN,
}

AZURE_LANGUAGES = {
    'en': Language.EN_US,
    'hi': Language.HI_IN,
    'ta': Language.TA_IN,
    'te': Language.TE_IN,
    'kn': Language.KN_IN,
    'ml': Language.ML_IN,
    'gu': Language.GU_IN,
    'bn': Language.BN_IN,
    'mr': Language.MR_IN,
    'pa': Language.PA_IN,
    'or': Language.OR_IN,
}

# ElevenLabs STT takes ISO-639-3 codes
ELEVENLABS_STT_LANGUAGES = {
    'en': 'eng',
    'hi': 'hin',
    'ta': 'tam',
    'te': 'tel',
    'kn': 'kan',
    'ml': 'mal',
    'gu': 'guj',
    'bn': 'ben',
    'mr': 'mar',
    'pa': 'pan',
    'or': 'ori',
}


def pick(parameters: Mapping[str, Any], keys: Iterable[str]) -> Dict[str, Any]:
    """The given keys that are present in ``parameters``."""
    return {key: parameters[key] for key in keys if key in parameters}


def pick_truthy(parameters: Mapping[str, Any], keys: Iterable[str]) -> Dict[str, Any]:
    """The given keys whose value in ``parameters`` is set and truthy."""
    return {key: parameters[key] for key in keys if parameters.get(key)}


def map_language(
    lang_code: Optional[str], languages: Mapping[str, T], label: str
) -> Optional[T]:
    """Look up ``lang_code`` in a provider map, warning when it is unknown."""
    if not lang_code:
        return None
    mapped = languages.get(lang_code)
    if mapped is None:
        logger.warning(f"No {label} language mapping for '{lang_code}', skipping")
    return mapped


def pipecat_language(value: Any, label: str) -> Optional[Language]:
    """Coerce a stored language value to Pipecat's ``Language`` enum."""
    if not isinstance(value, str):
        return value
    try:
        return Language(value)
    except ValueError:
        logger.warning(f"Unknown {label} language '{value}', skipping")
        return None
