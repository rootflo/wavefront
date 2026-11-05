import logging

from call_processing.services.common.context.bindings import (
    resolve_bindings,
    tool_bindings,
)
from call_processing.services.common.context.subject import CallSubject
from call_processing.services.common.tools.tool_wrapper_service import (
    ToolWrapperFactory,
)

SUBJECT = CallSubject('CA123', 'inbound', '+911234567890')


def _tool(bind=None):
    association = {'is_enabled': True}
    if bind is not None:
        association['config_overrides'] = {'context': {'bind': bind}}
    return {
        'name': 'find_account',
        'description': 'Find the account',
        'tool_type': 'python',
        'config': {},
        'parameter_schema': {
            'properties': {
                'mobile_number': {'type': 'string'},
                'service': {'type': 'string'},
            },
            'required': ['mobile_number', 'service'],
        },
        'association': association,
    }


class _RecordingWrapper:
    def __init__(self):
        self.calls = []

    async def execute(self, params):
        self.calls.append(params)
        return {'success': True, 'status_code': 200, 'data': {}}


def test_no_bind_config_means_no_bindings():
    assert tool_bindings(_tool()) == {}


def test_unknown_variable_is_ignored_and_logged(caplog):
    with caplog.at_level(logging.WARNING, logger='call_processing'):
        assert tool_bindings(_tool({'mobile_number': 'caller.email'})) == {}
    assert "unknown variable 'caller.email'" in caplog.text


def test_resolves_every_call_variable():
    bind = {
        'phone': 'caller.phone',
        'ref': 'call.id',
        'dir': 'call.direction',
        'agent': 'agent.id',
    }
    assert resolve_bindings(bind, SUBJECT, 'agent-1') == {
        'phone': '+911234567890',
        'ref': 'CA123',
        'dir': 'inbound',
        'agent': 'agent-1',
    }


def test_browser_call_leaves_phone_with_the_ai():
    # WebRTC has no call subject: the argument stays in the AI's schema
    assert resolve_bindings({'mobile_number': 'caller.phone'}, None, 'agent-1') == {}


def test_empty_phone_leaves_it_with_the_ai():
    subject = CallSubject('CA123', 'inbound', '')
    assert resolve_bindings({'mobile_number': 'caller.phone'}, subject, None) == {}


def test_schema_hides_bound_argument():
    schema, _ = ToolWrapperFactory.create_pipecat_function(
        _tool(), _RecordingWrapper(), {'mobile_number': '+911234567890'}
    )

    assert list(schema.properties) == ['service']
    assert schema.required == ['service']


async def test_bound_value_is_merged_and_wins():
    wrapper = _RecordingWrapper()
    _, fn = ToolWrapperFactory.create_pipecat_function(
        _tool(), wrapper, {'mobile_number': '+911234567890'}
    )

    await fn({'service': 'water', 'mobile_number': '98'})

    assert wrapper.calls == [{'service': 'water', 'mobile_number': '+911234567890'}]


async def test_unbound_tool_is_unchanged():
    wrapper = _RecordingWrapper()
    schema, fn = ToolWrapperFactory.create_pipecat_function(_tool(), wrapper)

    await fn({'mobile_number': '98', 'service': 'water'})

    assert list(schema.properties) == ['mobile_number', 'service']
    assert wrapper.calls == [{'mobile_number': '98', 'service': 'water'}]


def test_factory_wires_subject_into_bound_tools():
    schemas, registrations = ToolWrapperFactory.create_all_tool_functions(
        [_tool({'mobile_number': 'caller.phone'}), {**_tool(), 'name': 'plain'}],
        call_subject=SUBJECT,
        agent_id='agent-1',
    )

    assert [s.name for s in schemas] == ['find_account', 'plain']
    assert list(schemas[0].properties) == ['service']
    assert list(schemas[1].properties) == ['mobile_number', 'service']
    assert len(registrations) == 2


def test_factory_keeps_tool_with_unknown_variable_and_leaves_field_to_ai():
    schemas, _ = ToolWrapperFactory.create_all_tool_functions(
        [_tool({'mobile_number': 'caller.email'})], call_subject=SUBJECT
    )
    assert list(schemas[0].properties) == ['mobile_number', 'service']
