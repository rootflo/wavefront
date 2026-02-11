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
