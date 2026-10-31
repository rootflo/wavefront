"""STT/TTS api_keys and telephony credentials: stored, cached, returned and merged.

Runs every case with envelope encryption off and on (a fake KMS), against an
in-memory repository and cache.
"""

import json
import uuid
from unittest.mock import AsyncMock, Mock

import pytest

from common_module.response_formatter import ResponseFormatter
from common_module.security.secret_cipher import SECRET_MASK, SecretCipher
from db_repo_module.models.stt_config import SttConfig
from db_repo_module.models.telephony_config import TelephonyConfig
from db_repo_module.models.tts_config import TtsConfig
from flo_cloud._types import FloCipher
from flo_cloud.envelope import ENVELOPE_PREFIX, EnvelopeCipher
from voice_agents_module.controllers.stt_config_controller import get_stt_config
from voice_agents_module.controllers.telephony_config_controller import (
    get_telephony_config,
)
from voice_agents_module.controllers.tts_config_controller import get_tts_config
from voice_agents_module.services.stt_config_service import SttConfigService
from voice_agents_module.services.telephony_config_service import (
    TelephonyConfigService,
)
from voice_agents_module.services.tts_config_service import TtsConfigService

API_KEY = 'sk-live-123'
TWILIO = {'account_sid': 'AC123', 'auth_token': 'tw-secret'}
EXOTEL = {
    'api_key': 'ex-key',
    'api_token': 'ex-token',
    'account_sid': 'acct',
    'subdomain': 'ccm-api.exotel.com',
}


class FakeKms(FloCipher):
    def encrypt(self, plaintext):
        data = plaintext.encode() if isinstance(plaintext, str) else plaintext
        return b'kms:' + bytes(reversed(data))

    def decrypt(self, ciphertext):
        return bytes(reversed(ciphertext[4:]))

    def encrypt_for_storage(self, plaintext):
        raise NotImplementedError

    def decrypt_from_storage(self, stored):
        raise NotImplementedError


class FakeRepository:
    def __init__(self, model):
        self.model = model
        self.record = None

    async def create(self, **fields):
        self.record = self.model(id=uuid.uuid4(), is_deleted=False, **fields)
        return self.record

    async def find_one(self, **filters):
        return self.record

    async def find(self, **filters):
        return [self.record] if self.record else []

    async def find_one_and_update(self, filters, refresh=False, **fields):
        for key, value in fields.items():
            setattr(self.record, key, value)
        return self.record


class FakeCache:
    def __init__(self):
        self.values = {}

    def add(self, key, value, expiry=None):
        self.values[key] = value

    def get_str(self, key):
        return self.values.get(key)

    def remove(self, key):
        return self.values.pop(key, None) is not None


def _cipher(enabled: bool) -> SecretCipher:
    return SecretCipher(
        enabled=enabled, envelope_factory=lambda: EnvelopeCipher(FakeKms())
    )


def assert_no_secret(value, secrets):
    """Recursively check a response carries no secret and no ciphertext."""
    if isinstance(value, dict):
        for item in value.values():
            assert_no_secret(item, secrets)
    elif isinstance(value, list):
        for item in value:
            assert_no_secret(item, secrets)
    elif isinstance(value, str):
        assert not value.startswith(ENVELOPE_PREFIX)
        assert value not in secrets


def body(response) -> dict:
    return json.loads(response.body)['data']


@pytest.fixture(params=[False, True], ids=['flag_off', 'flag_on'])
def enabled(request):
    return request.param


@pytest.fixture
def cache():
    return FakeCache()


def make_service(service_cls, model, cache, enabled):
    repository = FakeRepository(model)
    service = service_cls(
        repository,
        cache,
        Mock(invalidate=AsyncMock(return_value=True)),
        _cipher(enabled),
    )
    return service, repository


# ---- STT / TTS ---------------------------------------------------------------


@pytest.fixture(
    params=[
        (SttConfigService, SttConfig, get_stt_config, 'stt_config_service'),
        (TtsConfigService, TtsConfig, get_tts_config, 'tts_config_service'),
    ],
    ids=['stt', 'tts'],
)
def api_key_case(request, cache, enabled):
    service_cls, model, endpoint, service_arg = request.param
    service, repository = make_service(service_cls, model, cache, enabled)
    return service, repository, endpoint, service_arg


class TestApiKeyConfigs:
    async def test_api_key_is_stored_in_the_flag_mode(self, api_key_case, enabled):
        service, repository, _, _ = api_key_case

        await service.create_config(display_name='x', provider='p', api_key=API_KEY)
        stored = repository.record.api_key

        if enabled:
            assert stored.startswith(ENVELOPE_PREFIX)
        else:
            assert stored == API_KEY

        await service.update_config(repository.record.id, api_key='sk-new')
        updated = repository.record.api_key
        if enabled:
            assert updated.startswith(ENVELOPE_PREFIX)
        else:
            assert updated == 'sk-new'

    async def test_cache_holds_the_stored_form(self, api_key_case, cache):
        service, repository, _, _ = api_key_case

        await service.create_config(display_name='x', provider='p', api_key=API_KEY)

        (cached,) = cache.values.values()
        assert json.loads(cached)['api_key'] == repository.record.api_key

    async def test_public_responses_carry_no_api_key(self, api_key_case):
        service, repository, _, _ = api_key_case

        created = await service.create_config(
            display_name='x', provider='p', api_key=API_KEY
        )
        config_id = repository.record.id
        responses = [
            created,
            await service.get_config(config_id),  # cache hit
            await service.list_configs(),  # cache miss
            await service.list_configs(),  # cache hit
            await service.update_config(config_id, display_name='y'),
        ]

        for response in responses:
            assert_no_secret(response, {API_KEY})
        assert created['has_api_key'] is True
        assert 'api_key' not in created

    async def test_runtime_config_reveals_the_api_key(self, api_key_case):
        service, repository, _, _ = api_key_case

        await service.create_config(display_name='x', provider='p', api_key=API_KEY)

        runtime = await service.get_runtime_config(repository.record.id)
        assert runtime['api_key'] == API_KEY

    async def test_include_secrets_returns_the_stored_form(self, api_key_case):
        service, repository, endpoint, service_arg = api_key_case
        await service.create_config(display_name='x', provider='p', api_key=API_KEY)
        config_id = repository.record.id

        def call(include_secrets):
            return endpoint(
                config_id=config_id,
                include_secrets=include_secrets,
                response_formatter=ResponseFormatter(),
                **{service_arg: service},
            )

        stored = body(await call(True))
        public = body(await call(False))

        assert stored['api_key'] == repository.record.api_key
        assert 'api_key' not in public
        assert public['has_api_key'] is True
        assert_no_secret(public, {API_KEY})


# ---- telephony -----------------------------------------------------------------


@pytest.fixture
def telephony(cache, enabled):
    return make_service(TelephonyConfigService, TelephonyConfig, cache, enabled)


async def create_telephony(service, provider='twilio', credentials=TWILIO):
    return await service.create_config(
        display_name='x',
        provider=provider,
        connection_type='websocket',
        credentials=dict(credentials),
    )


def stored_credentials(repository) -> dict:
    return json.loads(repository.record.credentials)


class TestTelephonyConfigs:
    async def test_secret_fields_are_stored_in_the_flag_mode(self, telephony, enabled):
        service, repository = telephony

        await create_telephony(service, 'exotel', EXOTEL)
        stored = stored_credentials(repository)

        for field in ('api_key', 'api_token'):
            if enabled:
                assert stored[field].startswith(ENVELOPE_PREFIX)
            else:
                assert stored[field] == EXOTEL[field]
        # Identifiers stay readable
        assert stored['account_sid'] == 'acct'
        assert stored['subdomain'] == 'ccm-api.exotel.com'

    async def test_public_responses_mask_the_secret_fields(self, telephony):
        service, repository = telephony

        created = await create_telephony(service)
        config_id = repository.record.id
        responses = [
            created,
            await service.get_config(config_id),
            await service.list_configs(),
            await service.list_configs(),
            await service.update_config(config_id, display_name='y'),
        ]

        for response in responses:
            assert_no_secret(response, {TWILIO['auth_token']})
        assert created['credentials'] == {
            'account_sid': 'AC123',
            'auth_token': SECRET_MASK,
        }

    async def test_runtime_config_reveals_the_credentials(self, telephony):
        service, repository = telephony

        await create_telephony(service, 'exotel', EXOTEL)

        runtime = await service.get_runtime_config(repository.record.id)
        assert runtime['credentials'] == EXOTEL

    async def test_include_secrets_returns_the_stored_form(self, telephony):
        service, repository = telephony
        await create_telephony(service)

        def call(include_secrets):
            return get_telephony_config(
                config_id=repository.record.id,
                include_secrets=include_secrets,
                response_formatter=ResponseFormatter(),
                telephony_config_service=service,
            )

        stored = body(await call(True))
        public = body(await call(False))

        assert stored['credentials'] == stored_credentials(repository)
        assert public['credentials']['auth_token'] == SECRET_MASK
        assert_no_secret(public, {TWILIO['auth_token']})

    async def test_update_keeps_masked_and_missing_secrets(self, telephony):
        service, repository = telephony
        await create_telephony(service, 'exotel', EXOTEL)

        # api_key sent back masked, api_token and subdomain left out
        await service.update_config(
            repository.record.id,
            credentials={'api_key': SECRET_MASK, 'account_sid': 'acct-2'},
        )

        runtime = await service.get_runtime_config(repository.record.id)
        assert runtime['credentials'] == {**EXOTEL, 'account_sid': 'acct-2'}

    async def test_update_replaces_a_typed_secret(self, telephony, enabled):
        service, repository = telephony
        await create_telephony(service)

        await service.update_config(
            repository.record.id, credentials={'auth_token': 'tw-new'}
        )

        if enabled:
            assert stored_credentials(repository)['auth_token'].startswith(
                ENVELOPE_PREFIX
            )
        runtime = await service.get_runtime_config(repository.record.id)
        assert runtime['credentials'] == {
            'account_sid': 'AC123',
            'auth_token': 'tw-new',
        }

    async def test_provider_change_takes_the_new_credentials(self, telephony):
        service, repository = telephony
        await create_telephony(service)

        await service.update_config(
            repository.record.id, provider='smartflo', credentials={'api_key': 'sf'}
        )

        runtime = await service.get_runtime_config(repository.record.id)
        assert runtime['credentials'] == {'api_key': 'sf'}

    async def test_provider_change_requires_credentials(self, telephony):
        service, repository = telephony
        await create_telephony(service)

        # Carrying Twilio credentials over to smartflo would store auth_token
        # unprotected, since smartflo only protects api_key.
        with pytest.raises(ValueError):
            await service.update_config(repository.record.id, provider='smartflo')

    async def test_provider_change_rejects_masked_secrets(self, telephony):
        service, repository = telephony
        await create_telephony(service)

        with pytest.raises(ValueError):
            await service.update_config(
                repository.record.id,
                provider='smartflo',
                credentials={'api_key': SECRET_MASK},
            )
