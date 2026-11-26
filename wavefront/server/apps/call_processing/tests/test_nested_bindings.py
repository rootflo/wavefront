"""Binding fields nested inside an object argument.

Made-up scenario: a water utility helpline whose tools take one object
argument, ``request``, with the fields inside it. ``find_account`` needs only
the caller's phone; ``get_bill`` also needs the service the caller asks about.
"""

import copy
import logging

import pytest

from call_processing.services.common.context.bindings import (
    hidden_schema,
    merge_bound,
    tool_bindings,
    unbound_required,
)
from call_processing.services.common.context.compiler import start_prefetch
from call_processing.services.common.context.store import CallContextStore
from call_processing.services.common.context.subject import CallSubject
from call_processing.services.common.tools.tool_wrapper_service import (
    ApiToolWrapper,
    ToolWrapperFactory,
)

from tests.test_call_context_store import FakeRedis
from tests.test_context_compiler import _drain

# Indian mobiles start with 6-9, so this can't be a real caller
PHONE = '+911234567890'
SUBJECT = CallSubject('CA123', 'inbound', PHONE)
PHONE_BIND = {'request.phone': 'caller.phone'}

LANGUAGE = {'enum': ['en', 'hi'], 'type': 'string'}

FIND_ACCOUNT_SCHEMA = {
    'type': 'object',
    'required': ['request'],
    'properties': {
        'request': {
            'type': 'object',
            'required': ['phone'],
            'properties': {
                'phone': {'type': 'string', 'description': "The caller's phone."},
            },
        }
    },
}

GET_BILL_SCHEMA = {
    'type': 'object',
    'required': ['request'],
    'properties': {
        'request': {
            'type': 'object',
            'required': ['service'],
            'properties': {
                'language': LANGUAGE,
                'period': {'type': 'string', 'description': 'Optional. YYYY-MM.'},
                'service': {'enum': ['water', 'sewer'], 'type': 'string'},
                'phone': {'type': 'string', 'description': 'Optional.'},
            },
        }
    },
}


def _with_optional_language(schema):
    """The schema plus an optional language field the AI may add."""
    schema = copy.deepcopy(schema)
    schema['properties']['request']['properties']['language'] = LANGUAGE
    return schema


def _tool(name, schema, bind=PHONE_BIND):
    return {
        'name': name,
        'description': name,
        'tool_type': 'api',
        'config': {'url': f'https://water.test/{name}', 'method': 'POST'},
        'parameter_schema': schema,
        'association': {
            'is_enabled': True,
            'config_overrides': {
                'context': {'bind': bind, 'prefetch': True, 'read_only': True}
            },
        },
    }


@pytest.fixture
def api_calls(monkeypatch):
    calls = []

    async def fake_execute(self, params):
        calls.append(copy.deepcopy(params))
        return {'account': {'customer_name': 'Jane Doe', 'amount_due': 1250}}

    monkeypatch.setattr(ApiToolWrapper, 'execute', fake_execute)
    return calls


def _ai_tools(tools, store):
    schemas, registrations = ToolWrapperFactory.create_all_tool_functions(
        tools, call_subject=SUBJECT, agent_id='agent-1', context_store=store
    )
    return {s.name: s for s in schemas}, dict(registrations)


# --------------------------------------------------------------- the helpers


def test_nested_string_field_can_be_bound():
    tool = _tool('find_account', FIND_ACCOUNT_SCHEMA)
    assert tool_bindings(tool) == PHONE_BIND


@pytest.mark.parametrize(
    'bind, problem',
    [
        ({'request': 'caller.phone'}, 'object field, not text'),
        ({'request.mobile': 'caller.phone'}, 'no such field'),
        ({'request.phone': 'caller.email'}, 'unknown variable'),
    ],
)
def test_binds_that_cannot_apply_are_ignored(caplog, bind, problem):
    tool = _tool('find_account', FIND_ACCOUNT_SCHEMA, bind)
    with caplog.at_level(logging.WARNING, logger='call_processing'):
        assert tool_bindings(tool) == {}
    assert problem in caplog.text


def test_hidden_schema_drops_only_the_bound_field():
    original = copy.deepcopy(GET_BILL_SCHEMA)

    hidden = hidden_schema(GET_BILL_SCHEMA, PHONE_BIND)

    request = hidden['properties']['request']
    assert list(request['properties']) == ['language', 'period', 'service']
    assert request['required'] == ['service']
    assert GET_BILL_SCHEMA == original  # the tool config is never edited


def test_object_left_empty_is_removed():
    assert hidden_schema(FIND_ACCOUNT_SCHEMA, PHONE_BIND) == {
        'type': 'object',
        'required': [],
        'properties': {},
    }


def test_merge_writes_into_the_object_and_wins():
    assert merge_bound(
        {'request': {'service': 'water', 'phone': '98'}}, {'request.phone': PHONE}
    ) == {'request': {'service': 'water', 'phone': PHONE}}


def test_merge_creates_the_object_when_the_ai_left_it_out():
    assert merge_bound({}, {'request.phone': PHONE}) == {'request': {'phone': PHONE}}


def test_unbound_required_looks_inside_objects():
    assert unbound_required(FIND_ACCOUNT_SCHEMA, PHONE_BIND) == []
    # service comes from the caller, so get_bill can never prefetch
    assert unbound_required(GET_BILL_SCHEMA, PHONE_BIND) == ['request.service']
    # Binding the whole object counted it as filled; it isn't
    assert unbound_required(FIND_ACCOUNT_SCHEMA, {}) == ['request.phone']
    # A required field the server can't fill blocks prefetch
    required_language = _with_optional_language(FIND_ACCOUNT_SCHEMA)
    required_language['properties']['request']['required'].append('language')
    assert unbound_required(required_language, PHONE_BIND) == ['request.language']


# ------------------------------------------------------- on a call (factory)


async def test_find_account_prefetch_is_served_to_the_ais_call(api_calls):
    store = CallContextStore(FakeRedis())
    tool = _tool('find_account', FIND_ACCOUNT_SCHEMA)

    assert start_prefetch([tool], SUBJECT, 'agent-1', store) == 1
    await _drain()
    schemas, fns = _ai_tools([tool], store)
    # Its only field is server-filled, so the AI sees no arguments at all
    assert schemas['find_account'].properties == {}
    assert schemas['find_account'].required == []

    # Whether the AI sends nothing or an empty object, the key matches
    await fns['find_account']({})
    await fns['find_account']({'request': {}})

    assert api_calls == [{'request': {'phone': PHONE}}]


async def test_ai_adding_an_optional_field_goes_live(api_calls):
    # Accepted miss (owner decision): different details, different key
    store = CallContextStore(FakeRedis())
    tool = _tool('find_account', _with_optional_language(FIND_ACCOUNT_SCHEMA))

    start_prefetch([tool], SUBJECT, 'agent-1', store)
    await _drain()
    _, fns = _ai_tools([tool], store)
    await fns['find_account']({'request': {'language': 'hi'}})

    assert api_calls[1] == {'request': {'language': 'hi', 'phone': PHONE}}


async def test_get_bill_cannot_prefetch_but_ai_still_sends_service(api_calls):
    store = CallContextStore(FakeRedis())
    tool = _tool('get_bill', GET_BILL_SCHEMA)

    assert start_prefetch([tool], SUBJECT, 'agent-1', store) == 0
    schemas, fns = _ai_tools([tool], store)
    request = schemas['get_bill'].properties['request']
    assert 'service' in request['properties']
    assert 'phone' not in request['properties']

    await fns['get_bill']({'request': {'service': 'water'}})

    assert api_calls == [{'request': {'service': 'water', 'phone': PHONE}}]


async def test_object_bind_leaves_the_object_with_the_ai(api_calls):
    # Binding a whole object (a 422 at the API before): ignored, tool works as before
    store = CallContextStore(FakeRedis())
    tool = _tool('get_bill', GET_BILL_SCHEMA, bind={'request': 'caller.phone'})

    assert start_prefetch([tool], SUBJECT, 'agent-1', store) == 0
    schemas, fns = _ai_tools([tool], store)
    assert schemas['get_bill'].required == ['request']

    await fns['get_bill']({'request': {'service': 'water'}})
    assert api_calls == [{'request': {'service': 'water'}}]
