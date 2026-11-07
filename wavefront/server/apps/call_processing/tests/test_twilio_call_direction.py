"""Twilio streams learn the call's direction from our TwiML.

The inbound webhook prefetches with direction 'inbound'; the stream must bind
the same value, or call.direction tools see 'outbound' and miss that cache.
"""

from xml.etree import ElementTree

from call_processing.controllers.webhook_controller import _stream_twiml
from call_processing.services.telephony.session_service import _stream_params


def _twilio_start(**body):
    return {'stream_id': 'MZ1', 'call_id': 'CA1', 'body': body}


def test_twiml_sends_the_direction_to_the_stream():
    for direction in ('inbound', 'outbound'):
        twiml = _stream_twiml(
            'https://calls.example.test',
            voice_agent_id='agent-1',
            customer_number='+15550100',
            agent_number='+15550199',
            call_direction=direction,
        ).body.decode()

        stream = ElementTree.fromstring(twiml)
        parameters = {p.get('name'): p.get('value') for p in stream.iter('Parameter')}
        assert parameters['call_direction'] == direction


def test_twilio_stream_reads_the_direction():
    params = _stream_params(
        'twilio', _twilio_start(voice_agent_id='agent-1', call_direction='inbound')
    )

    assert params.call_direction == 'inbound'


def test_twilio_stream_without_a_valid_direction_falls_back():
    # Calls whose TwiML predates the parameter, or a value we never send
    assert _stream_params('twilio', _twilio_start()).call_direction is None
    bogus = _stream_params('twilio', _twilio_start(call_direction='sideways'))
    assert bogus.call_direction is None
