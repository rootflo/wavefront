"""Secrets in cached voice-agent configs.

The cache keeps what floware returned (ciphertext with envelope encryption on);
``get_all_agent_configs`` hands callers copies with the secrets revealed.
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
from call_processing.services.common import floware_http_client as http_module
from call_processing.services.common.floware_http_client import FlowareHttpClient
from call_processing.services.common.voice_agent_cache_service import (
    VoiceAgentCacheService,
)
from common_module.security.secret_cipher import SecretCipher, SecretModeMismatchError
from flo_cloud._types import FloCipher
from flo_cloud.envelope import ENVELOPE_PREFIX, EnvelopeCipher

AGENT_ID = uuid.uuid4()
LLM_ID, TTS_ID, STT_ID, TEL_ID = (uuid.uuid4() for _ in range(4))

PLAIN = {
    'llm': 'sk-llm',
    'tts': 'sk-tts',
    'stt': 'sk-stt',
    'credentials': {
        'api_key': 'ex-key',
        'api_token': 'ex-token',
        'account_sid': 'acct',
        'subdomain': 'ccm-api.exotel.com',
    },
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


def enabled_cipher() -> SecretCipher:
    return SecretCipher(
        enabled=True, envelope_factory=lambda: EnvelopeCipher(FakeKms())
    )


def disabled_cipher() -> SecretCipher:
    def never_called():
        raise AssertionError('KMS must not be built while encryption is disabled')

    return SecretCipher(enabled=False, envelope_factory=never_called)


class FakeCache:
    def __init__(self):
        self.values = {}

    async def aget_json(self, key):
        value = self.values.get(key)
        return copy.deepcopy(value) if value is not None else None

    async def aset_json(self, key, value, expiry=None):
        self.values[key] = copy.deepcopy(value)
        return True


class FakeFloware:
    """Returns configs the way floware does with include_secrets=true."""

    def __init__(self, configs):
        self.configs = configs

    async def fetch_voice_agent(self, agent_id):
        return copy.deepcopy(self.configs['agent'])

    async def fetch_config(self, config_type, config_id):
        return copy.deepcopy(self.configs[config_type])

    async def get_agent_tools(self, agent_id):
        return []


def stored_configs(cipher: SecretCipher, credentials_as_json: bool = False) -> dict:
    """Configs in the form floware stores (and returns with include_secrets)."""
    credentials = cipher.protect_fields(PLAIN['credentials'], ('api_key', 'api_token'))
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
            'api_key': cipher.protect('sk-llm'),
        },
        'tts_config': {'id': str(TTS_ID), 'api_key': cipher.protect('sk-tts')},
        'stt_config': {'id': str(STT_ID), 'api_key': cipher.protect('sk-stt')},
        'telephony_config': {
            'id': str(TEL_ID),
            'provider': 'exotel',
            'credentials': (
                json.dumps(credentials) if credentials_as_json else credentials
            ),
        },
    }


def warm_cache(cache: FakeCache, configs: dict) -> None:
    cache.values.update(
        {
            get_voice_agent_cache_key(AGENT_ID): configs['agent'],
            get_llm_config_cache_key(LLM_ID): configs['llm_inference_config'],
            get_tts_config_cache_key(TTS_ID): configs['tts_config'],
            get_stt_config_cache_key(STT_ID): configs['stt_config'],
            get_telephony_config_cache_key(TEL_ID): configs['telephony_config'],
            get_tools_config_cache_key(AGENT_ID): [],
        }
    )


def assert_revealed(result: dict) -> None:
    assert result['llm_config']['api_key'] == 'sk-llm'
    assert result['tts_config']['api_key'] == 'sk-tts'
    assert result['stt_config']['api_key'] == 'sk-stt'
    assert result['telephony_config']['credentials'] == PLAIN['credentials']


def cached_secrets(cache: FakeCache) -> list:
    telephony = cache.values[get_telephony_config_cache_key(TEL_ID)]
    credentials = telephony['credentials']
    if isinstance(credentials, str):
        credentials = json.loads(credentials)
    return [
        cache.values[get_llm_config_cache_key(LLM_ID)]['api_key'],
        cache.values[get_tts_config_cache_key(TTS_ID)]['api_key'],
        cache.values[get_stt_config_cache_key(STT_ID)]['api_key'],
        credentials['api_key'],
        credentials['api_token'],
    ]


@pytest.mark.parametrize('credentials_as_json', [False, True])
async def test_cache_hit_reveals_and_cache_keeps_ciphertext(credentials_as_json):
    cipher = enabled_cipher()
    cache = FakeCache()
    warm_cache(cache, stored_configs(cipher, credentials_as_json))
    service = VoiceAgentCacheService(cache, secret_cipher=cipher)

    result = await service.get_all_agent_configs(AGENT_ID)

    assert_revealed(result)
    assert all(v.startswith(ENVELOPE_PREFIX) for v in cached_secrets(cache))
    assert result['telephony_config']['credentials']['account_sid'] == 'acct'


async def test_api_fallback_caches_ciphertext_and_reveals():
    cipher = enabled_cipher()
    cache = FakeCache()
    floware = FakeFloware(stored_configs(cipher))
    service = VoiceAgentCacheService(cache, floware, secret_cipher=cipher)

    result = await service.get_all_agent_configs(AGENT_ID)

    assert_revealed(result)
    assert all(v.startswith(ENVELOPE_PREFIX) for v in cached_secrets(cache))


async def test_flag_off_passes_values_through_unchanged():
    cipher = disabled_cipher()
    cache = FakeCache()
    configs = stored_configs(cipher)
    warm_cache(cache, configs)
    service = VoiceAgentCacheService(cache, secret_cipher=cipher)

    result = await service.get_all_agent_configs(AGENT_ID)

    assert_revealed(result)
    assert result['telephony_config'] == configs['telephony_config']
    assert cached_secrets(cache) == ['sk-llm', 'sk-tts', 'sk-stt', 'ex-key', 'ex-token']


async def test_flag_off_rejects_ciphertext():
    cache = FakeCache()
    warm_cache(cache, stored_configs(enabled_cipher()))
    service = VoiceAgentCacheService(cache, secret_cipher=disabled_cipher())

    with pytest.raises(SecretModeMismatchError):
        await service.get_all_agent_configs(AGENT_ID)


async def test_webrtc_path_without_telephony():
    cipher = enabled_cipher()
    cache = FakeCache()
    warm_cache(cache, stored_configs(cipher))
    service = VoiceAgentCacheService(cache, secret_cipher=cipher)

    result = await service.get_all_agent_configs(AGENT_ID, require_telephony=False)

    assert result['telephony_config'] is None
    assert result['llm_config']['api_key'] == 'sk-llm'


@pytest.mark.parametrize(
    'config_type',
    ['llm_inference_config', 'tts_config', 'stt_config', 'telephony_config'],
)
async def test_fetch_config_requests_stored_secrets(monkeypatch, config_type):
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
