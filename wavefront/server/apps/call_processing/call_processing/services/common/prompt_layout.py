"""How a multi-language system prompt is laid out, so provider prompt caching works.

LLM providers reuse a cached prompt only up to the first changed character, so
what changes least comes first and what changes most comes last::

    [main prompt]            the agent author's text: same for every call
    [language pack]          that language's rules and samples, or nothing
    [switching rules]        the same in every language
    [call details]           phone number, time, caller context: fixed per call
    [current language line]  "Respond in Tamil. Current language: Tamil."

A language switch rebuilds the prompt from these parts with the new pack and
the new last line, so the main prompt stays cached and there is only ever one
pack. The language line goes last on purpose: models follow the end of a long
prompt more reliably than its middle.

Packs come from ``conversation_config.language_prompts`` ({"ta": "...", ...}).
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping

from call_processing.log.logger import logger
from call_processing.services.common.conversation_config import config_section
from call_processing.services.common.prompts import current_language_line


@dataclass(frozen=True)
class PromptParts:
    main: str
    rules: str
    suffix: str
    packs: Mapping[str, str] = field(default_factory=dict)


def build_system_prompt(parts: PromptParts, language: str) -> str:
    pack = (parts.packs.get(language) or '').strip()
    pack_block = f'\n\n{pack}' if pack else ''
    return (
        f'{parts.main}{pack_block}{parts.rules}{parts.suffix}'
        f'\n\n{current_language_line(language)}'
    )


def language_packs(
    agent_config: Mapping[str, Any], supported_languages: List[str]
) -> Dict[str, str]:
    """``conversation_config.language_prompts`` for the agent's languages only."""
    packs: Dict[str, str] = {}
    for language, text in config_section(agent_config, 'language_prompts').items():
        if language not in supported_languages:
            logger.warning(
                f'Language pack {language!r} ignored: not a supported language'
            )
        elif not isinstance(text, str):
            logger.warning(f'Language pack {language!r} ignored: not text')
        elif text.strip():
            packs[language] = text.strip()
    return packs
