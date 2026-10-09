"""The streaming preference, from the JSONB column to ``ResolvedPolicy``.

Three things to prove. That the value survives a save-and-read round trip
through ``policy_config`` without a migration, since it rides in a column that
is replaced wholesale on every write. That a row written before the field
existed still resolves, to the behaviour it was already getting. And that a
value nobody recognises is defaulted rather than raised on -- unlike a
malformed adapter entry, which refuses the whole policy.
"""

import pytest
from flo_ai.guardrails.contracts import StreamCapability
from guardrails_module.models.schemas import (
    StreamPreference,
    UpdateGuardrailPolicyPayload,
)
from guardrails_module.services.guardrails_service import (
    GuardrailsService,
    build_resolved_policy,
)

PII_ADAPTER = {
    'name': 'presidio_pii',
    'stages': ['AFTER_MODEL'],
    'on_error': 'FAIL_OPEN',
    'timeout_seconds': 5.0,
    'options': {},
}


class FakeRepository:
    """Records the row that would have been written."""

    def __init__(self, row=None):
        self.row = row
        self.upserts = []

    async def upsert(self, keys, **values):
        self.upserts.append({**keys, **values})
        self.row = _Row({**keys, **values})

    async def find_one(self, **kwargs):
        return self.row


class _Row:
    def __init__(self, data):
        self._data = data

    def to_dict(self):
        return {'created_at': None, 'updated_at': None, **self._data}


class FakeCache:
    def __init__(self):
        self.removed = []

    def get_str(self, key):
        return None

    def set_str(self, key, value, ttl=None):
        return None

    def remove(self, key):
        self.removed.append(key)


def service(row=None):
    return GuardrailsService(FakeRepository(row), FakeCache())


class TestResolution:
    def test_absent_means_buffered(self):
        """Rows written before the field existed keep the behaviour they had."""
        resolved = build_resolved_policy(mode='ENFORCE', adapter_entries=[])

        assert resolved.stream is StreamCapability.BUFFERED

    def test_incremental_is_carried_through(self):
        resolved = build_resolved_policy(
            mode='ENFORCE', adapter_entries=[], stream='INCREMENTAL'
        )

        assert resolved.stream is StreamCapability.INCREMENTAL

    def test_an_unknown_value_defaults_without_raising(self):
        """A bad stream value costs latency; a bad adapter entry costs a check.

        The adapter parsing beside this deliberately re-raises, because
        skipping an entry would leave an operator believing a check runs when
        it does not. Nothing comparable is at stake here: the worst case is a
        response delivered more slowly than asked for.
        """
        resolved = build_resolved_policy(
            mode='ENFORCE', adapter_entries=[], stream='SOMETHING_ELSE'
        )

        assert resolved.stream is StreamCapability.BUFFERED

    def test_a_malformed_adapter_entry_still_refuses_the_policy(self):
        """Guard against the tolerance above spreading to the entries."""
        with pytest.raises((KeyError, ValueError)):
            build_resolved_policy(
                mode='ENFORCE',
                adapter_entries=[{'stages': ['AFTER_MODEL']}],
                stream='INCREMENTAL',
            )


class TestRoundTrip:
    async def test_save_and_read_needs_no_migration(self):
        svc = service()

        await svc.update_policy(
            namespace='acme',
            is_enabled=True,
            mode='ENFORCE',
            adapters=[PII_ADAPTER],
            stream='INCREMENTAL',
        )
        written = svc.guardrail_policy_repository.upserts[-1]

        assert written['policy_config'] == {
            'adapters': [PII_ADAPTER],
            'stream': 'INCREMENTAL',
        }

    async def test_a_save_that_omits_it_reverts_to_buffered(self):
        """policy_config is replaced wholesale, so the default is a real write.

        Documented rather than lamented: it is why the console has to send
        the field on every save even when the user never touched it.
        """
        svc = service()

        await svc.update_policy(
            namespace='acme', is_enabled=True, mode='ENFORCE', adapters=[]
        )

        assert svc.guardrail_policy_repository.upserts[-1]['policy_config'] == {
            'adapters': [],
            'stream': 'BUFFERED',
        }

    def test_to_response_reports_it(self):
        response = GuardrailsService.to_response(
            {
                'namespace': 'acme',
                'is_enabled': True,
                'mode': 'ENFORCE',
                'policy_config': {'adapters': [], 'stream': 'INCREMENTAL'},
            }
        )

        assert response['stream'] == 'INCREMENTAL'

    def test_to_response_defaults_a_row_that_predates_the_field(self):
        response = GuardrailsService.to_response(
            {
                'namespace': 'acme',
                'is_enabled': True,
                'mode': 'ENFORCE',
                'policy_config': {'adapters': []},
            }
        )

        assert response['stream'] == 'BUFFERED'


class TestPayload:
    def test_the_payload_defaults_to_buffered(self):
        payload = UpdateGuardrailPolicyPayload(is_enabled=True)

        assert payload.stream is StreamPreference.BUFFERED

    def test_the_payload_accepts_incremental(self):
        payload = UpdateGuardrailPolicyPayload(is_enabled=True, stream='INCREMENTAL')

        assert payload.stream is StreamPreference.INCREMENTAL

    def test_the_payload_rejects_an_unknown_value(self):
        """Caught at the edge, where it can still be a 400 on the settings page."""
        with pytest.raises(ValueError):
            UpdateGuardrailPolicyPayload(is_enabled=True, stream='SOMETIMES')
