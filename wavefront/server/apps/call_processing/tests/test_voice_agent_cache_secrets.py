"""Secrets in cached voice-agent configs.

floware returns configs with plaintext secrets (``include_secrets=true``).
Redis gets only the public part; the secrets stay in a process-local memo
tagged with the config's ``updated_at``.
"""

import copy
import json
import uuid

import flo_lib.http as httpx
import pytest

from call_processing.cache.cache_utils import (
    get_llm_config_cache_key,
    get_stt_config_cache_key,
    get_telephony_config_cache_key,
    get_tools_config_cache_key,
    get_tts_config_cache_key,
    get_voice_agent_cache_key,
)
from call_processing.controllers.cache_controller import (
    InvalidateCacheRequest,
    invalidate_cache,
)
from call_processing.services.common import floware_http_client as http_module
from call_processing.services.common.floware_http_client import FlowareHttpClient
from call_processing.services.common.secret_memo import SecretMemo
from call_processing.services.common.voice_agent_cache_service import (
    VoiceAgentCacheService,
)

AGENT_ID = uuid.uuid4()
LLM_ID, TTS_ID, STT_ID, TEL_ID = (uuid.uuid4() for _ in range(4))
UPDATED_AT = '2026-11-01T10:00:00'

CREDENTIALS = {
    'api_key': 'ex-key',
    'api_token': 'ex-token',
    'account_sid': 'acct',
    'subdomain': 'ccm-api.exotel.com',
}

CONFIG_KEYS = {
    'llm_inference_config': get_llm_config_cache_key(LLM_ID),
    'tts_config': get_tts_config_cache_key(TTS_ID),
    'stt_config': get_stt_config_cache_key(STT_ID),
    'telephony_config': get_telephony_config_cache_key(TEL_ID),
}


class FakeCache:
    def __init__(self):
        self.values = {}

    async def aget_json(self, key):
        value = self.values.get(key)
        return copy.deepcopy(value) if value is not None else None

    def set_json(self, key, value, expiry=None):
        self.values[key] = copy.deepcopy(value)
        return True

    async def aset_json(self, key, value, expiry=None):
        return self.set_json(key, value, expiry)

    def remove(self, key):
        return self.values.pop(key, None) is not None


class FakeFloware:
    """Returns configs the way floware does with include_secrets=true."""

    def __init__(self, configs):
        self.configs = configs
        self.fetched = []

    async def fetch_voice_agent(self, agent_id):
        return copy.deepcopy(self.configs['agent'])

    async def fetch_config(self, config_type, config_id):
        self.fetched.append(config_type)
        return copy.deepcopy(self.configs[config_type])

    async def get_agent_tools(self, agent_id):
        return []


def floware_configs(
    suffix: str = '', updated_at: str = UPDATED_AT, credentials_as_json=False
) -> dict:
    credentials = {**CREDENTIALS, 'api_key': 'ex-key' + suffix}
    return {
        'agent': {
            'id': str(AGENT_ID),
            'llm_config_id': str(LLM_ID),
            'tts_config_id': str(TTS_ID),
            'stt_config_id': str(STT_ID),
            'telephony_config_id': str(TEL_ID),
        },
        'llm_inference_config': {
            'id': str(LLM_ID),
            'api_key': 'sk-llm' + suffix,
            'updated_at': updated_at,
        },
        'tts_config': {
            'id': str(TTS_ID),
            'api_key': 'sk-tts' + suffix,
            'updated_at': updated_at,
        },
        'stt_config': {
            'id': str(STT_ID),
            'api_key': 'sk-stt' + suffix,
            'updated_at': updated_at,
        },
        'telephony_config': {
            'id': str(TEL_ID),
            'provider': 'exotel',
            'credentials': (
                json.dumps(credentials) if credentials_as_json else credentials
            ),
            'updated_at': updated_at,
        },
    }


def assert_secrets(result: dict, suffix: str = '') -> None:
    assert result['llm_config']['api_key'] == 'sk-llm' + suffix
    assert result['tts_config']['api_key'] == 'sk-tts' + suffix
    assert result['stt_config']['api_key'] == 'sk-stt' + suffix
    assert result['telephony_config']['credentials'] == {
        **CREDENTIALS,
        'api_key': 'ex-key' + suffix,
    }


def assert_redis_has_no_secrets(cache: FakeCache) -> None:
    for key in CONFIG_KEYS.values():
        if key in cache.values:
            assert 'api_key' not in cache.values[key]
            assert 'credentials' not in cache.values[key]
    assert 'sk-' not in json.dumps(cache.values)
    assert 'ex-key' not in json.dumps(cache.values)


@pytest.mark.parametrize('credentials_as_json', [False, True])
async def test_api_fallback_keeps_secrets_out_of_redis(credentials_as_json):
    cache = FakeCache()
    floware = FakeFloware(floware_configs(credentials_as_json=credentials_as_json))
    service = VoiceAgentCacheService(cache, floware)

    result = await service.get_all_agent_configs(AGENT_ID)

    assert_secrets(result)
    assert_redis_has_no_secrets(cache)
    assert result['telephony_config']['provider'] == 'exotel'
    llm_public = cache.values[CONFIG_KEYS['llm_inference_config']]
    assert llm_public == {'id': str(LLM_ID), 'updated_at': UPDATED_AT}


async def test_memo_hit_does_not_fetch():
    cache = FakeCache()
    floware = FakeFloware(floware_configs())
    service = VoiceAgentCacheService(cache, floware)
    await service.get_all_agent_configs(AGENT_ID)
    floware.fetched.clear()

    result = await service.get_all_agent_configs(AGENT_ID)

    assert floware.fetched == []
    assert_secrets(result)


async def test_updated_at_change_in_redis_refetches():
    cache = FakeCache()
    floware = FakeFloware(floware_configs())
    service = VoiceAgentCacheService(cache, floware)
    await service.get_all_agent_configs(AGENT_ID)

    # Another pod refreshed Redis after the config changed in floware
    floware.configs = floware_configs('-new', updated_at='2026-11-02T10:00:00')
    for key in CONFIG_KEYS.values():
        cache.values[key]['updated_at'] = '2026-11-02T10:00:00'
    floware.fetched.clear()

    result = await service.get_all_agent_configs(AGENT_ID)

    assert sorted(floware.fetched) == sorted(CONFIG_KEYS)
    assert_secrets(result, '-new')
    assert_redis_has_no_secrets(cache)


async def test_secrets_in_old_redis_entries_are_ignored():
    cache = FakeCache()
    stale = floware_configs()
    stale['llm_inference_config']['api_key'] = 'enc:v1:stale'
    stale['tts_config']['api_key'] = 'enc:v1:stale'
    stale['stt_config']['api_key'] = 'enc:v1:stale'
    stale['telephony_config']['credentials'] = {
        **CREDENTIALS,
        'api_key': 'enc:v1:stale',
    }
    cache.values[get_voice_agent_cache_key(AGENT_ID)] = stale['agent']
    cache.values[get_tools_config_cache_key(AGENT_ID)] = []
    for config_type, key in CONFIG_KEYS.items():
        cache.values[key] = stale[config_type]
    floware = FakeFloware(floware_configs())
    service = VoiceAgentCacheService(cache, floware)

    result = await service.get_all_agent_configs(AGENT_ID)

    assert sorted(floware.fetched) == sorted(CONFIG_KEYS)
    assert_secrets(result)
    assert 'enc:v1:' not in json.dumps(result)
    assert_redis_has_no_secrets(cache)


async def test_webrtc_path_without_telephony():
    cache = FakeCache()
    floware = FakeFloware(floware_configs())
    service = VoiceAgentCacheService(cache, floware)

    result = await service.get_all_agent_configs(AGENT_ID, require_telephony=False)

    assert result['telephony_config'] is None
    assert 'telephony_config' not in floware.fetched
    assert result['llm_config']['api_key'] == 'sk-llm'


async def test_returned_secrets_do_not_alias_the_memo():
    cache = FakeCache()
    service = VoiceAgentCacheService(cache, FakeFloware(floware_configs()))
    await service.get_all_agent_configs(AGENT_ID)

    first = await service.get_all_agent_configs(AGENT_ID)
    first['telephony_config']['credentials']['api_key'] = 'mutated'
    second = await service.get_all_agent_configs(AGENT_ID)

    assert second['telephony_config']['credentials']['api_key'] == 'ex-key'


@pytest.mark.parametrize(
    'config_type, config_id',
    [
        ('llm_inference_config', LLM_ID),
        ('tts_config', TTS_ID),
        ('stt_config', STT_ID),
        ('telephony_config', TEL_ID),
    ],
)
async def test_cache_invalidation_refresh_writes_public_data_only(
    config_type, config_id
):
    cache = FakeCache()
    floware = FakeFloware(floware_configs())
    service = VoiceAgentCacheService(cache, floware)
    cache.values[CONFIG_KEYS[config_type]] = {'id': str(config_id), 'stale': True}

    await invalidate_cache(
        InvalidateCacheRequest(config_type=config_type, config_id=str(config_id)),
        voice_agent_cache_service=service,
        _auth=None,
    )

    public = dict(floware_configs()[config_type])
    public.pop('api_key', None)
    public.pop('credentials', None)
    assert cache.values[CONFIG_KEYS[config_type]] == public
    assert_redis_has_no_secrets(cache)


async def test_cache_invalidation_refresh_feeds_the_memo():
    cache = FakeCache()
    floware = FakeFloware(floware_configs())
    service = VoiceAgentCacheService(cache, floware)
    await service.get_all_agent_configs(AGENT_ID)

    floware.configs = floware_configs('-new', updated_at='2026-11-02T10:00:00')
    await invalidate_cache(
        InvalidateCacheRequest(
            config_type='llm_inference_config', config_id=str(LLM_ID)
        ),
        voice_agent_cache_service=service,
        _auth=None,
    )
    floware.fetched.clear()

    result = await service.get_all_agent_configs(AGENT_ID)

    assert floware.fetched == []
    assert result['llm_config']['api_key'] == 'sk-llm-new'


def test_secret_memo_evicts_least_recently_used():
    memo = SecretMemo(max_entries=2)
    memo.put(('a', '1'), 't1', {'api_key': 'a'})
    memo.put(('b', '2'), 't2', {'api_key': 'b'})
    memo.get(('a', '1'))
    memo.put(('c', '3'), 't3', {'api_key': 'c'})

    assert memo.get(('b', '2')) is None
    assert memo.get(('a', '1')) == ('t1', {'api_key': 'a'})
    assert memo.get(('c', '3')) == ('t3', {'api_key': 'c'})


def test_secret_memo_expires_entries():
    memo = SecretMemo(ttl_seconds=0)
    memo.put(('a', '1'), 't1', {'api_key': 'a'})

    assert memo.get(('a', '1')) is None


@pytest.mark.parametrize(
    'config_type',
    ['llm_inference_config', 'tts_config', 'stt_config', 'telephony_config'],
)
async def test_fetch_config_requests_secrets(monkeypatch, config_type):
    seen = []

    def handler(request):
        seen.append(request.url.params.get('include_secrets'))
        return httpx.Response(200, json={'data': {'id': 'x'}})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        http_module.httpx,
        'AsyncClient',
        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
    )
    client = FlowareHttpClient('http://floware', passthrough_secret='')

    assert await client.fetch_config(config_type, uuid.uuid4()) == {'id': 'x'}
    assert seen == ['true']
