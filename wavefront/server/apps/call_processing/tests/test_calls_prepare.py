"""/api/calls/prepare: auth, validation, and what it keeps for the call."""

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from call_processing.controllers.context_controller import (
    PrepareCallRequest,
    allowed_principal_prefixes,
    mtls_principal,
    verify_internal_caller,
)
from call_processing.services.common.context import compiler
from call_processing.services.common.context.bindings import (
    resolve_bindings,
    tool_bindings,
)
from call_processing.services.common.context.compiler import prepare_outbound_call
from call_processing.services.common.context.store import CallContextStore
from call_processing.services.common.context.subject import CallSubject

from tests.test_call_context_store import FakeRedis

FLOWARE_XFCC = (
    'By=spiffe://cluster.local/ns/call-processing/sa/default;'
    'Hash=abc;URI=spiffe://cluster.local/ns/wavefront-api/sa/floware'
)


def _verify(**overrides):
    kwargs = {
        'x_passthrough': None,
        'x_forwarded_client_cert': None,
        'app_env': 'production',
        'passthrough_secret': 'dev-secret',
        'mtls_allowed_namespaces': 'wavefront-api',
    }
    kwargs.update(overrides)
    return verify_internal_caller(**kwargs)


# --------------------------------------------------------------------- auth


def test_production_accepts_floware_mtls_identity():
    assert _verify(x_forwarded_client_cert=FLOWARE_XFCC) is None


@pytest.mark.parametrize(
    'overrides',
    [
        {},  # no identity at all
        {'x_passthrough': 'dev-secret'},  # passthrough is dev-only
        {
            'x_forwarded_client_cert': 'URI=spiffe://cluster.local/ns/other/sa/x',
        },
        {
            'x_forwarded_client_cert': FLOWARE_XFCC,
            'mtls_allowed_namespaces': '',  # not configured: nobody gets in
        },
    ],
)
def test_production_rejects_everyone_else(overrides):
    with pytest.raises(HTTPException) as error:
        _verify(**overrides)
    assert error.value.status_code == 401


def test_dev_uses_the_passthrough_secret():
    assert _verify(app_env='dev', x_passthrough='dev-secret') is None
    for wrong in (None, 'nope'):
        with pytest.raises(HTTPException):
            _verify(app_env='dev', x_passthrough=wrong)


def test_dev_without_a_configured_secret_rejects():
    with pytest.raises(HTTPException):
        _verify(app_env='dev', x_passthrough='', passthrough_secret='')


def test_principal_and_prefix_parsing():
    assert mtls_principal(FLOWARE_XFCC) == (
        'spiffe://cluster.local/ns/wavefront-api/sa/floware'
    )
    assert mtls_principal('spiffe://cluster.local/ns/a/sa/b') == (
        'spiffe://cluster.local/ns/a/sa/b'
    )
    assert mtls_principal('Hash=abc') is None
    assert allowed_principal_prefixes(' a, ,b ') == (
        'spiffe://cluster.local/ns/a',
        'spiffe://cluster.local/ns/b',
    )


# ---------------------------------------------------------------- validation


AGENT_ID = '0b7f4c2e-1d3a-4c5b-9e8f-7a6b5c4d3e2f'


def _request(context):
    return PrepareCallRequest(
        agent_id=AGENT_ID,
        call_ref='CA123',
        customer_number='+911234567890',
        context=context,
    )


def test_context_keys_and_size_are_checked():
    assert _request({'reason_for_call': 'overdue bill'}).context == {
        'reason_for_call': 'overdue bill'
    }
    with pytest.raises(ValidationError):
        _request({'Reason For Call': 'x'})
    with pytest.raises(ValidationError):
        _request({'notes': 'x' * 3000})
    with pytest.raises(ValidationError):
        _request({'nested': {'a': 'b'}})


# ------------------------------------------------------------ what it keeps


class _NoConfigs:
    """The agent has no tools: prepare still keeps the context."""

    async def get_all_agent_configs(self, agent_id):
        return {'tools': []}


async def test_prepare_keeps_the_context_for_the_ringing_call():
    store = CallContextStore(FakeRedis())
    subject = CallSubject.for_call(
        call_ref='CA123', direction='outbound', raw_phone='+911234567890'
    )

    saved = await prepare_outbound_call(
        _NoConfigs(), AGENT_ID, subject, store, {'reason_for_call': 'overdue bill'}
    )
    await compiler.asyncio.gather(*list(compiler._background))

    assert saved is True
    assert await store.read_outbound(AGENT_ID, 'CA123') == {
        'reason_for_call': 'overdue bill'
    }
    assert await store.read_outbound(AGENT_ID, 'CA999') == {}


# ------------------------------------------------------- outbound.<key> binds


def test_outbound_variables_bind_and_resolve():
    tool = {
        'name': 'get_bill',
        'parameter_schema': {
            'properties': {'account_id': {'type': 'string'}},
            'required': ['account_id'],
        },
        'association': {
            'config_overrides': {
                'context': {'bind': {'account_id': 'outbound.account_id'}}
            }
        },
    }
    bind = tool_bindings(tool)
    assert bind == {'account_id': 'outbound.account_id'}

    subject = CallSubject('CA123', 'outbound', '+911234567890')
    assert resolve_bindings(bind, subject, 'agent-1', {'account_id': 'W-42'}) == {
        'account_id': 'W-42'
    }
    # Inbound calls have no CRM context: the field stays with the AI
    assert resolve_bindings(bind, subject, 'agent-1') == {}


def test_bare_outbound_prefix_is_not_a_variable():
    tool = {
        'name': 'get_bill',
        'parameter_schema': {'properties': {'account_id': {'type': 'string'}}},
        'association': {
            'config_overrides': {'context': {'bind': {'account_id': 'outbound.'}}}
        },
    }
    assert tool_bindings(tool) == {}
