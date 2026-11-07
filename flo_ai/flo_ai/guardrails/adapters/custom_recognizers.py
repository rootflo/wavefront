"""Recognisers for identifiers Presidio does not ship.

Imports Presidio at module level, so it is only ever imported lazily from inside
the engine build in ``presidio_adapter`` - the same reason ``pii_catalog`` stays
Presidio-free.

Each class here is registered by ``PresidioAdapter._register_custom_recognizers``
under the never-shadow rule, so if a later Presidio release adds its own
recogniser for one of these entities, the upstream one wins and this one is
skipped.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from presidio_analyzer import EntityRecognizer, Pattern, PatternRecognizer


def _is_luhn_valid(digits: str) -> bool:
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


class AeEmiratesIdRecognizer(PatternRecognizer):
    """UAE Emirates ID number: ``784-YYYY-NNNNNNN-C``.

    Fifteen digits: ``784`` (the ISO 3166 numeric code for the UAE), the
    holder's birth year, a seven-digit sequence and a Luhn check digit. Written
    with dashes, spaces or no separators at all.

    The check digit is required. The ``784`` prefix plus a 19xx/20xx year
    still leaves about one random 15-digit figure in 50,000 - an order or
    account number - matching the shape; the Luhn check cuts that tenfold.
    The trade-off is that a mistyped ID is not redacted.
    """

    PATTERNS = [
        Pattern(
            'Emirates ID',
            r'\b784[- ]?(?:19|20)\d{2}[- ]?\d{7}[- ]?\d\b',
            0.5,
        ),
    ]

    CONTEXT = [
        'emirates',
        'emirates id',
        'eid',
        'uae',
        'identity',
        'ica',
    ]

    def __init__(
        self,
        patterns: Optional[List[Pattern]] = None,
        context: Optional[List[str]] = None,
        supported_language: str = 'en',
        supported_entity: str = 'AE_EMIRATES_ID',
        replacement_pairs: Optional[List[Tuple[str, str]]] = None,
    ) -> None:
        self.replacement_pairs = replacement_pairs or [('-', ''), (' ', '')]
        super().__init__(
            supported_entity=supported_entity,
            patterns=patterns or self.PATTERNS,
            context=context or self.CONTEXT,
            supported_language=supported_language,
        )

    def validate_result(self, pattern_text: str) -> bool:
        """``True`` promotes to full confidence; ``False`` drops the match."""
        digits = EntityRecognizer.sanitize_value(pattern_text, self.replacement_pairs)
        return (
            len(digits) == 15
            and digits.isdigit()
            and digits.startswith('784')
            and _is_luhn_valid(digits)
        )


#: Registered, in order, by ``PresidioAdapter._register_custom_recognizers``.
CUSTOM_RECOGNIZERS: tuple = (AeEmiratesIdRecognizer,)
