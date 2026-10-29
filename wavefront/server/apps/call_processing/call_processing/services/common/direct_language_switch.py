"""Switch language without the extra LLM call when the user only names one.

Per agent, via ``conversation_config.language_switch`` on the voice agent::

    {
      "language_switch": {
        "direct_switch": false,  // on: "Hindi" switches before the LLM runs
        "choice_words": {        // optional, per language code
          "hi": ["mein", "chahiye"]
        }
      }
    }

Off (the default), a language choice costs two LLM calls in a row: the first
only calls ``detect_and_switch_language``, the second writes the reply in the
new language. On, a user turn that is nothing but a supported language name
("Hindi", "हिंदी", "Hindi please", "Hindi mein") switches TTS, STT and the system
prompt here, before the LLM runs, so a single call answers in the new language.
Anything else ("can we talk in Hindi?", a sentence that mentions a language)
goes to the LLM and its tool as before.

Choice words are what may surround the name ("please", "mein", "la"). A turn
may use the words of English and of every language the agent supports, combined:
an en + hi + ta agent accepts "Tamil mein" and "Hindi please" alike, an agent
without Hindi does not accept "mein". Each language's words are the built-ins in
``LANGUAGE_CHOICE_WORDS`` unless ``choice_words`` lists that language: then the
agent's list replaces the built-ins for it (add words, or drop one that misfires).
Entries are split into words; language names are dropped, since a name used as
a choice word would let "Hindi Tamil" pass as a choice.

Only multi-language agents that use the tool take the shortcut: browser rooms
whose app drives the language (``room_context_language``) never do.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
)

from pipecat.frames.frames import Frame, LLMContextFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from call_processing.constants.language_config import (
    LANGUAGE_CHOICE_WORDS,
    LANGUAGE_DISPLAY_NAMES,
    LANGUAGE_KEYWORDS,
)
from call_processing.log.logger import logger
from call_processing.services.common.conversation_config import config_section
from call_processing.services.common.language_switch import (
    language_update_frames,
    set_prompt_language,
)
from call_processing.services.common.prompts import direct_language_switch_note

_SECTION = 'conversation_config.language_switch'


@dataclass(frozen=True)
class LanguageSwitchConfig:
    # Off: a language choice goes through the LLM tool (two LLM calls)
    direct_switch: bool = False
    # Per language code: replaces that language's built-in choice words
    choice_words: Dict[str, Tuple[str, ...]] = field(default_factory=dict)

    @classmethod
    def from_agent_config(cls, agent_config: Mapping[str, Any]) -> LanguageSwitchConfig:
        raw = config_section(agent_config, 'language_switch')
        d = cls()
        return cls(
            direct_switch=raw['direct_switch']
            if isinstance(raw.get('direct_switch'), bool)
            else d.direct_switch,
            choice_words=_choice_word_book(raw.get('choice_words')),
        )


_LANGUAGE_NAMES = frozenset(
    name for names in LANGUAGE_KEYWORDS.values() for name in names
)


def _choice_word_book(value: Any) -> Dict[str, Tuple[str, ...]]:
    """``choice_words`` as {language: words}; anything malformed is skipped."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        logger.warning(f'Ignoring invalid {_SECTION}.choice_words: {value!r}')
        return {}
    book: Dict[str, Tuple[str, ...]] = {}
    for language, entries in value.items():
        if not isinstance(language, str) or not isinstance(entries, list):
            logger.warning(
                f'Ignoring invalid {_SECTION}.choice_words[{language!r}]: {entries!r}'
            )
            continue
        words = [
            word
            for entry in entries
            if isinstance(entry, str)
            for word in _words(entry)
            if word not in _LANGUAGE_NAMES
        ]
        book[language.lower()] = tuple(dict.fromkeys(words))
    return book


def _words(text: str) -> List[str]:
    """Lower-cased words, punctuation (including the danda) dropped."""
    cleaned = ''.join(
        ' ' if unicodedata.category(ch).startswith('P') else ch for ch in text.lower()
    )
    return cleaned.split()


def _choice_words(
    supported_languages: Sequence[str],
    choice_words: Optional[Mapping[str, Sequence[str]]] = None,
) -> Set[str]:
    """Words allowed around a language name: English plus the agent's languages,
    each the agent's own list if it has one, else the built-ins."""
    agent_words = choice_words or {}
    return {
        word
        for code in ('en', *supported_languages)
        for word in agent_words.get(code, LANGUAGE_CHOICE_WORDS.get(code, []))
    }


def match_language_choice(
    text: str,
    supported_languages: Sequence[str],
    choice_words: Optional[Mapping[str, Sequence[str]]] = None,
) -> Optional[str]:
    """The supported language ``text`` does nothing but name, else None.

    Around the name only choice words of English and the agent's own languages
    may appear (see the module docstring); anything else ("not", "loan", "can")
    means the turn is more than a choice and goes to the LLM.
    """
    allowed = _choice_words(supported_languages, choice_words)
    words = [w for w in _words(text) if w not in allowed]
    if not words:
        return None
    # "Hindi. Hindi." names one language; "bahasa indonesia" is one name
    phrase = words[0] if len(set(words)) == 1 else ' '.join(words)
    matches = [
        code
        for code in supported_languages
        if phrase in LANGUAGE_KEYWORDS.get(code, [])
    ]
    # A name two supported codes share (Filipino / Tagalog) is left to the LLM
    return matches[0] if len(matches) == 1 else None


def _message_text(message: Any) -> Optional[str]:
    """A user message's text, or None for anything that is not a user message."""
    if not isinstance(message, dict) or message.get('role') != 'user':
        return None
    content = message.get('content')
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return ' '.join(
            part.get('text', '')
            for part in content
            if isinstance(part, dict) and part.get('type') == 'text'
        )
    return None


class DirectLanguageSwitchProcessor(FrameProcessor):
    """Between the user aggregator and the LLM: switches language for a user turn
    that only names one, before the LLM runs on it. Passes everything through
    untouched when ``enabled`` is off."""

    def __init__(
        self,
        *,
        enabled: bool,
        supported_languages: List[str],
        language_state: Dict[str, Any],
        task_container: Dict[str, Any],
        tts_provider: str,
        stt_provider: str,
        tts_voice_ids: Dict[str, str],
        on_language_selected: Optional[Callable[[str], Awaitable[None]]] = None,
        choice_words: Optional[Mapping[str, Sequence[str]]] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._enabled = enabled
        self._supported_languages = supported_languages
        self._language_state = language_state
        self._task_container = task_container
        self._tts_provider = tts_provider
        self._stt_provider = stt_provider
        self._tts_voice_ids = tts_voice_ids
        self._on_language_selected = on_language_selected
        self._choice_words = choice_words or {}

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if (
            self._enabled
            and direction == FrameDirection.DOWNSTREAM
            and isinstance(frame, LLMContextFrame)
        ):
            await self._maybe_switch(frame.context)
        await self.push_frame(frame, direction)

    async def _maybe_switch(self, context: Any) -> None:
        messages = context.get_messages()
        # Only a user turn: a check-in or other run ends with another role
        text = _message_text(messages[-1]) if messages else None
        if not text:
            return
        language = match_language_choice(
            text, self._supported_languages, self._choice_words
        )
        if language is None:
            return
        current = self._language_state.get('current_language')
        name = LANGUAGE_DISPLAY_NAMES.get(language, language)

        if language != current:
            task = self._task_container.get('task')
            if task is None:
                return
            tts_frame, stt_frame = language_update_frames(
                tts_provider=self._tts_provider,
                stt_provider=self._stt_provider,
                tts_voice_ids=self._tts_voice_ids,
                language=language,
            )
            if not set_prompt_language(context, self._language_state, language):
                logger.error('Direct language switch: no base prompt to switch')
                return
            # STT is upstream of here: queue from the pipeline's start
            if stt_frame:
                await task.queue_frame(stt_frame)
            # Ahead of the context frame, so the voice changes before the reply
            if tts_frame:
                await self.push_frame(tts_frame)
            self._language_state['current_language'] = language
            self._language_state['switch_count'] = (
                self._language_state.get('switch_count', 0) + 1
            )
            logger.info(
                f'Direct language switch {current} -> {language}: '
                f'TTS={"pushed" if tts_frame else "skipped"}, '
                f'STT={"queued" if stt_frame else "skipped"}'
            )
        else:
            logger.info(f'Direct language switch: already using {language}')

        # Tells the LLM the switch is done, so it answers instead of calling the tool
        context.add_message(
            {'role': 'developer', 'content': direct_language_switch_note(name)}
        )
        if self._on_language_selected is not None:
            try:
                await self._on_language_selected(language)
            except Exception as e:  # never let a UI notification break the turn
                logger.warning(f'on_language_selected hook failed: {e}')
