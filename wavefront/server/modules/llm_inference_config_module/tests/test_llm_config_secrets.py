"""The api_key is stored and cached protected, revealed only for runtime use,
and never returned in public responses."""

import json
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from common_module.common_container import CommonContainer
from common_module.security.secret_cipher import (
    SecretCipher,
    SecretModeMismatchError,
    UnencryptedSecretError,
)
from db_repo_module.models.llm_inference_config import LlmInferenceConfig
from flo_cloud._types import FloCipher
from flo_cloud.envelope import ENVELOPE_PREFIX, EnvelopeCipher
from llm_inference_config_module.container import LlmInferenceConfigContainer
from llm_inference_config_module.controllers import llm_inference_config_controller
from llm_inference_config_module.controllers.llm_inference_config_controller import (
    llm_inference_config_router,
)
from llm_inference_config_module.services.llm_inference_config_service import (
    LlmInferenceConfigService,
)
from llm_inference_config_module.utils.cache_utils import (
    get_llm_inference_config_cache_key,
    get_llm_inference_configs_list_cache_key,
)

API_KEY = 'sk-live-123'


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


def enabled_cipher() -> SecretCipher:
    return SecretCipher(
        enabled=True, envelope_factory=lambda: EnvelopeCipher(FakeKms())
    )


def disabled_cipher() -> SecretCipher:
    def never_called():
        raise AssertionError('KMS must not be built while encryption is disabled')

    return SecretCipher(enabled=False, envelope_factory=never_called)


class FakeRepository:
    def __init__(self):
        self.rows = {}

    async def create(self, **fields):
        now = datetime(2026, 1, 1)
        row = LlmInferenceConfig(
            id=uuid.uuid4(), is_deleted=False, created_at=now, updated_at=now, **fields
        )
        self.rows[row.id] = row
        return row

    async def find_one(self, id, is_deleted=False):
        row = self.rows.get(id)
        return row if row and row.is_deleted == is_deleted else None

    async def find(self, is_deleted=False):
        return [r for r in self.rows.values() if r.is_deleted == is_deleted]

    async def find_one_and_update(self, filters, refresh=False, **fields):
        row = self.rows[filters['id']]
        for name, value in fields.items():
            setattr(row, name, value)
        return row


class FakeCache:
    def __init__(self):
        self.store = {}

    def get_str(self, key):
        return self.store.get(key)

    def add(self, key, value, expiry=None):
        self.store[key] = value

    def remove(self, key):
        self.store.pop(key, None)


def assert_no_secret(value):
    """Recursively assert a public response holds no key or ciphertext."""
    if isinstance(value, dict):
        assert 'api_key' not in value
        for item in value.values():
            assert_no_secret(item)
    elif isinstance(value, list):
        for item in value:
            assert_no_secret(item)
    elif isinstance(value, str):
        assert ENVELOPE_PREFIX not in value
        assert API_KEY not in value


@pytest.fixture(params=[True, False], ids=['flag_on', 'flag_off'])
def flag_on(request):
    return request.param


@pytest.fixture
def repository():
    return FakeRepository()


@pytest.fixture
def cache():
    return FakeCache()


@pytest.fixture
def service(flag_on, repository, cache):
    invalidator = Mock()
    invalidator.invalidate = AsyncMock(return_value=True)
    cipher = enabled_cipher() if flag_on else disabled_cipher()
    return LlmInferenceConfigService(repository, cache, invalidator, cipher)


async def create(service):
    return await service.create_config(
        llm_model='gpt-4o',
        display_name='GPT-4o',
        api_key=API_KEY,
        type='openai',
        base_url='https://api.openai.com',
    )


def assert_stored_form(value, flag_on):
    if flag_on:
        assert value.startswith(ENVELOPE_PREFIX)
        assert API_KEY not in value
    else:
        assert value == API_KEY


# ---- model ------------------------------------------------------------------


def test_model_to_dict_is_public_and_to_stored_dict_keeps_the_key():
    row = LlmInferenceConfig(
        id=uuid.uuid4(), llm_model='m', display_name='d', type='openai', api_key='x'
    )

    assert 'api_key' not in row.to_dict()
    assert row.to_dict()['has_api_key'] is True
    assert row.to_stored_dict()['api_key'] == 'x'
    assert 'has_api_key' not in row.to_stored_dict()


def test_model_has_api_key_is_false_without_a_key():
    row = LlmInferenceConfig(
        id=uuid.uuid4(), llm_model='m', display_name='d', type='ollama', api_key=None
    )

    assert row.to_dict()['has_api_key'] is False


# ---- storage ----------------------------------------------------------------


async def test_create_stores_and_caches_the_protected_key(
    service, repository, cache, flag_on
):
    created = await create(service)

    row = repository.rows[uuid.UUID(created['id'])]
    assert_stored_form(row.api_key, flag_on)

    cached = json.loads(cache.store[get_llm_inference_config_cache_key(row.id)])
    assert_stored_form(cached['api_key'], flag_on)


async def test_update_protects_a_new_key(service, repository, flag_on):
    created = await create(service)
    config_id = uuid.UUID(created['id'])

    await service.update_config(config_id, api_key=API_KEY)

    assert_stored_form(repository.rows[config_id].api_key, flag_on)


async def test_update_without_api_key_keeps_the_stored_key(service, repository):
    created = await create(service)
    config_id = uuid.UUID(created['id'])
    stored_before = repository.rows[config_id].api_key

    await service.update_config(config_id, display_name='renamed')

    assert repository.rows[config_id].api_key == stored_before


async def test_update_with_null_api_key_clears_it(service, repository):
    created = await create(service)
    config_id = uuid.UUID(created['id'])

    updated = await service.update_config(config_id, api_key=None)

    assert repository.rows[config_id].api_key is None
    assert updated['has_api_key'] is False


# ---- public responses -------------------------------------------------------


async def test_public_responses_never_carry_the_key(service):
    created = await create(service)
    config_id = uuid.UUID(created['id'])

    responses = [
        created,
        await service.get_public_config(config_id),  # cache hit
        await service.list_configs(),  # cache miss
        await service.list_configs(),  # cache hit
        await service.update_config(config_id, display_name='renamed'),
        await service.get_public_config(config_id),  # cache miss after update
    ]

    assert_no_secret(responses)
    assert created['has_api_key'] is True
    assert all(c['has_api_key'] for c in responses[2])


async def test_list_masks_entries_cached_with_a_key(service, cache):
    # A list cached before masking existed still holds the key.
    cache.store[get_llm_inference_configs_list_cache_key()] = json.dumps(
        [{'id': 'x', 'api_key': API_KEY}]
    )

    configs = await service.list_configs()

    assert_no_secret(configs)
    assert configs[0]['has_api_key'] is True


# ---- internal reads ---------------------------------------------------------


async def test_get_config_returns_the_stored_form(service, flag_on):
    created = await create(service)

    stored = await service.get_config(uuid.UUID(created['id']))

    assert_stored_form(stored['api_key'], flag_on)
    assert 'has_api_key' not in stored


async def test_runtime_config_has_plaintext_and_is_not_cached(service, cache):
    created = await create(service)
    config_id = uuid.UUID(created['id'])
    cache.store.clear()

    runtime = await service.get_runtime_config(config_id)

    assert runtime['api_key'] == API_KEY
    # The cache only ever receives the stored form.
    if service.secret_cipher.enabled:
        assert API_KEY not in json.dumps(cache.store)
    # Same shape the Celery worker rebuilds with LlmInferenceConfig(**dict).
    assert 'has_api_key' not in runtime
    assert LlmInferenceConfig(**runtime).api_key == API_KEY


async def test_runtime_config_of_missing_config_is_none(service):
    assert await service.get_runtime_config(uuid.uuid4()) is None


async def test_runtime_config_rejects_plaintext_when_flag_on(repository, cache):
    service = LlmInferenceConfigService(repository, cache, Mock(), enabled_cipher())
    row = await repository.create(
        llm_model='m', display_name='d', type='openai', api_key=API_KEY
    )

    with pytest.raises(UnencryptedSecretError):
        await service.get_runtime_config(row.id)


async def test_runtime_config_rejects_ciphertext_when_flag_off(repository, cache):
    service = LlmInferenceConfigService(repository, cache, Mock(), disabled_cipher())
    row = await repository.create(
        llm_model='m',
        display_name='d',
        type='openai',
        api_key=enabled_cipher().protect(API_KEY),
    )

    with pytest.raises(SecretModeMismatchError):
        await service.get_runtime_config(row.id)


# ---- GET /v1/llm-inference-configs/{id} ------------------------------------


@pytest.fixture
def client(service):
    llm = LlmInferenceConfigContainer()
    common = CommonContainer()
    llm.llm_inference_config_service.override(service)
    llm.wire(modules=[llm_inference_config_controller])
    common.wire(modules=[llm_inference_config_controller])
    app = FastAPI()
    app.include_router(llm_inference_config_router)
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        llm.unwire()
        common.unwire()


async def test_get_without_include_secrets_is_public(client, service):
    created = await create(service)

    response = client.get(f'/v1/llm-inference-configs/{created["id"]}')

    assert response.status_code == 200
    body = response.json()['data']
    assert_no_secret(body)
    assert body['has_api_key'] is True


async def test_get_with_include_secrets_returns_the_stored_form(
    client, service, flag_on
):
    created = await create(service)

    response = client.get(
        f'/v1/llm-inference-configs/{created["id"]}', params={'include_secrets': True}
    )

    assert response.status_code == 200
    body = response.json()['data']
    assert body == await service.get_config(uuid.UUID(created['id']))
    assert_stored_form(body['api_key'], flag_on)
