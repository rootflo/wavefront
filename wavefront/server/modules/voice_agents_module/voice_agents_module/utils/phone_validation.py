"""Phone number validation utilities"""

import re
from typing import List, Tuple, Optional

# E.164 phone number format: +[country code][subscriber number]
# Total length: 1-15 digits (including country code)
# Must start with + followed by country code (1-3 digits, cannot start with 0)
E164_PATTERN = re.compile(r'^\+[1-9]\d{1,14}$')


def validate_e164_format(phone_number: str) -> bool:
    """
    Validate that a phone number is in E.164 format.

    E.164 format:
    - Starts with +
    - Followed by country code (1-3 digits, cannot start with 0)
    - Followed by subscriber number
    - Total length: 1-15 digits (excluding +)
    - Examples: +12025551234 (US), +442071838750 (UK), +919876543210 (India)

    Args:
        phone_number: Phone number string to validate

    Returns:
        True if valid E.164 format, False otherwise
    """
    return bool(E164_PATTERN.match(phone_number))


def validate_phone_numbers(
    phone_numbers: List[str], field_name: str = 'phone_numbers'
) -> Tuple[bool, Optional[str]]:
    """
    Validate that all phone numbers in a list are in E.164 format.

    Args:
        phone_numbers: List of phone numbers to validate
        field_name: Name of the field for error messages

    Returns:
        Tuple of (is_valid, error_message). error_message is None if valid.
    """
    if not isinstance(phone_numbers, list):
        return False, f'{field_name} must be a list'

    if not phone_numbers:
        # Empty list is valid (agent might not have inbound/outbound numbers yet)
        return True, None

    invalid_numbers = []
    for number in phone_numbers:
        if not isinstance(number, str):
            invalid_numbers.append(str(number))
        elif not validate_e164_format(number):
            invalid_numbers.append(number)

    if invalid_numbers:
        return False, (
            f"{field_name} contains invalid E.164 format numbers: "
            f"{', '.join(invalid_numbers)}. "
            f"Format must be +[country][number] with 1-15 digits total, "
            f"e.g., +12025551234 (US), +442071838750 (UK), +919876543210 (India)"
        )

    return True, None
