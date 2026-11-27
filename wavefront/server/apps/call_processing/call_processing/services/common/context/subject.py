"""Who a call is about: the identity the server fills into tool arguments."""

import re
from dataclasses import dataclass
from typing import Optional

from call_processing.log.logger import logger

# E.164: + then 8 to 15 digits, no leading zero
_E164 = re.compile(r'^\+[1-9]\d{7,14}$')


def normalize_indian_phone_number(phone_number: str) -> str:
    """
    Normalize Indian phone number to E.164 format.

    Converts Indian national format (0xxxxxxxxxx) to E.164 format (+91xxxxxxxxxx).

    Examples:
        "01234567890" -> "+911234567890"
        "+911234567890" -> "+911234567890"
        "911234567890" -> "+911234567890"
    """
    # Remove any whitespace
    phone_number = phone_number.strip()

    # If already in E.164 format with +91, return as is
    if phone_number.startswith('+91'):
        return phone_number

    # If starts with 91 but no +, add +
    if phone_number.startswith('91') and len(phone_number) >= 12:
        return f'+{phone_number}'

    # If starts with 0 (Indian national format), replace with +91
    if phone_number.startswith('0'):
        return f'+91{phone_number[1:]}'

    # If it's just the number without country code, add +91
    if len(phone_number) == 10:
        return f'+91{phone_number}'

    # Return as is if we can't determine format
    return phone_number


@dataclass(frozen=True)
class CallSubject:
    """One phone call's identity.

    ``phone`` is always normalised, so every provider hands tools the same
    ``+91…`` format, or empty when the number is withheld or not a valid number
    (``anonymous``, Twilio's ``+266696687``): a caller.phone bind then stays
    with the AI, which can ask for it. The prompt keeps the raw number the
    provider sent.
    """

    call_ref: str
    direction: str
    phone: str

    @classmethod
    def for_call(
        cls, *, call_ref: str, direction: str, raw_phone: Optional[str]
    ) -> 'CallSubject':
        phone = normalize_indian_phone_number(raw_phone or '')
        if raw_phone and not _E164.match(phone):
            # Masked: say why caller.phone binds stay with the AI on this call
            logger.warning(
                f'Caller number for call {call_ref} is not a valid phone number '
                f'(…{raw_phone.strip()[-4:]}); caller.phone stays with the AI'
            )
            phone = ''
        return cls(
            call_ref=call_ref,
            direction=direction,
            phone=phone,
        )
