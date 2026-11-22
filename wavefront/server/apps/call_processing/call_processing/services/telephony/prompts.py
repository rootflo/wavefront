"""System-message text of the telephony flow.

Appended after the agent's own prompt on every phone call. Browser (WebRTC)
sessions have no caller number and never get it.
"""

from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def current_ist_time(now: datetime | None = None) -> str:
    """Current date, time and day in IST, plus how to resolve relative dates."""
    ist_time = (now or datetime.now(timezone.utc)).astimezone(IST)
    current_time = ist_time.strftime('%Y-%m-%d %H:%M:%S')
    current_day = ist_time.strftime('%A')
    return (
        f'Current Date and Time (IST): {current_time}, {current_day}\n'
        '- The user always speaks time in IST.\n'
        "- If the user says 'tomorrow', calculate the date based on today's date.\n"
        "- If the user says 'Monday', 'next Friday', etc., calculate the correct date relative to today.\n"
        "- Always convert relative dates (like 'tomorrow', 'next week') to specific dates (YYYY-MM-DD) when calling tools."
    )


def call_context(customer_number: str, now: datetime | None = None) -> str:
    """Caller number and IST clock, added at the very end of the system prompt.

    It changes on every call, so it goes last: the static part before it stays a
    stable prefix the provider can prompt-cache across calls (a cache miss adds
    to every turn's TTFB).
    """
    return f'\n\nCustomer phone number: {customer_number}\n{current_ist_time(now)}'
