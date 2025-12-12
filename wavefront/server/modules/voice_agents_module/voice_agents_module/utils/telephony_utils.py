"""
Telephony utility functions for URL generation and SIP URI construction.
"""


def get_sip_uri(sip_config: dict, phone_number: str) -> str:
    """
    Construct SIP URI from SIP configuration and phone number.

    Args:
        sip_config: SIP configuration dict with sip_domain, optional port and transport
        phone_number: Phone number to call (e.g., '+1234567890')

    Returns:
        SIP URI string (e.g., 'sip:+1234567890@pstn.twilio.com')

    Examples:
        - Basic: 'sip:+1234567890@example.sip.daily.co'
        - With port: 'sip:+1234567890@sip.twilio.com:5061'
        - With transport: 'sip:+1234567890@sip.twilio.com;transport=tls'
    """
    domain = sip_config['sip_domain']

    # Add optional port if specified
    if 'port' in sip_config and sip_config['port']:
        domain = f"{domain}:{sip_config['port']}"

    uri = f'sip:{phone_number}@{domain}'

    # Add transport parameter if specified
    if 'transport' in sip_config and sip_config['transport']:
        uri += f";transport={sip_config['transport']}"

    return uri


def get_websocket_url(call_id: str, base_url: str) -> str:
    """
    Auto-generate WebSocket URL for media streaming.

    This URL is used by Twilio to stream real-time audio to our call processing app.

    Args:
        call_id: Unique identifier for the call
        base_url: Base URL of the call processing app (from CALL_PROCESSING_PUBLIC_URL env var)

    Returns:
        WebSocket URL string

    Example:
        'wss://call-processing.example.com/webhooks/twilio/media/abc-123'
    """
    return f'{base_url}/webhooks/twilio/media/{call_id}'


def validate_phone_number(phone_number: str) -> bool:
    """
    Validate phone number format (E.164 format recommended).

    Args:
        phone_number: Phone number string

    Returns:
        True if valid format, False otherwise

    Note:
        This is a basic validation. E.164 format: +[country code][number]
        Example: +14155552671
    """
    if not phone_number:
        return False

    # Basic E.164 validation: starts with +, contains only digits after +
    if not phone_number.startswith('+'):
        return False

    # Check remaining characters are digits
    phone_digits = phone_number[1:]
    if not phone_digits.isdigit():
        return False

    # E.164 allows 1-15 digits after country code
    if len(phone_digits) < 1 or len(phone_digits) > 15:
        return False

    return True
