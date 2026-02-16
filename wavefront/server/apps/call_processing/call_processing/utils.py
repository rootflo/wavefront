from datetime import datetime, timedelta, timezone


def get_current_ist_time_str() -> str:
    """Return current date, time, and day in IST as a formatted string."""
    ist_offset = timedelta(hours=5, minutes=30)
    ist_time = datetime.now(timezone.utc) + ist_offset
    current_time = ist_time.strftime('%Y-%m-%d %H:%M:%S')
    current_day = ist_time.strftime('%A')
    return (
        f'Current Date and Time (IST): {current_time}, {current_day}\n'
        '- The user always speaks time in IST.\n'
        "- If the user says 'tomorrow', calculate the date based on today's date.\n"
        "- If the user says 'Monday', 'next Friday', etc., calculate the correct date relative to today.\n"
        "- Always convert relative dates (like 'tomorrow', 'next week') to specific dates (YYYY-MM-DD) when calling tools."
    )


def normalize_indian_phone_number(phone_number: str) -> str:
    """
    Normalize Indian phone number to E.164 format.

    Converts Indian national format (0xxxxxxxxxx) to E.164 format (+91xxxxxxxxxx).

    Args:
        phone_number: Phone number in various formats

    Returns:
        Phone number in E.164 format (+91xxxxxxxxxx)

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
