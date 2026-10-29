"""The language tables stay complete and consistent with each other."""

from call_processing.constants.language_config import (
    LANGUAGE_CHOICE_WORDS,
    LANGUAGE_INSTRUCTIONS,
    LANGUAGE_KEYWORDS,
)


def test_every_language_has_keywords_and_an_instruction():
    assert set(LANGUAGE_KEYWORDS) == set(LANGUAGE_INSTRUCTIONS)


def test_bulgarian_is_covered_like_the_other_selectable_languages():
    assert LANGUAGE_KEYWORDS['bg'][0] == 'bulgarian'
    assert 'bg' in LANGUAGE_INSTRUCTIONS


def test_choice_words_belong_to_known_languages():
    assert set(LANGUAGE_CHOICE_WORDS) <= set(LANGUAGE_KEYWORDS)


def test_a_choice_word_is_never_a_language_name():
    names = {name for keywords in LANGUAGE_KEYWORDS.values() for name in keywords}
    words = {word for words in LANGUAGE_CHOICE_WORDS.values() for word in words}

    assert words & names == set()


def test_choice_words_are_single_lower_case_words():
    for words in LANGUAGE_CHOICE_WORDS.values():
        for word in words:
            assert word == word.lower() and len(word.split()) == 1
