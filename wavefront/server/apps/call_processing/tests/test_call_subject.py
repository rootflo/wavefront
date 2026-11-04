import pytest

from call_processing.services.common.context.subject import (
    CallSubject,
    normalize_indian_phone_number,
)
from call_processing.services.telephony.conversation import TelephonyConversation


@pytest.mark.parametrize(
    'raw, expected',
    [
        ('+911234567890', '+911234567890'),  # Twilio E.164
        ('01234567890', '+911234567890'),  # Exotel national format
        ('1234567890', '+911234567890'),  # Smartflo 10-digit
        ('911234567890', '+911234567890'),
        (' 01234567890 ', '+911234567890'),
        ('', ''),
        ('+14155550100', '+14155550100'),  # non-Indian stays as sent
    ],
)
def test_normalize_indian_phone_number(raw, expected):
    assert normalize_indian_phone_number(raw) == expected


def test_subject_normalises_phone():
    subject = CallSubject.for_call(
        call_ref='CA123', direction='inbound', raw_phone='01234567890'
    )
    assert subject == CallSubject('CA123', 'inbound', '+911234567890')


def test_subject_tolerates_missing_phone():
    subject = CallSubject.for_call(
        call_ref='CA123', direction='outbound', raw_phone=None
    )
    assert subject.phone == ''


def test_telephony_prompt_keeps_raw_number_and_tools_get_normalised():
    conversation = TelephonyConversation(
        None,
        provider='smartflo',
        call_id='call-1',
        call_direction='inbound',
        customer_number='1234567890',
        agent_number='',
    )

    options = conversation.stack_options()

    assert 'Customer phone number: 1234567890\n' in options.prompt_suffix
    assert options.call_subject == CallSubject('call-1', 'inbound', '+911234567890')
