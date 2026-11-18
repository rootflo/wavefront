"""TokenService verifies tokens locally with a cached KMS public key.

A fake signer does real RSA-PSS signing (the same scheme KMS uses) and counts
how often the "remote" calls happen, so the tests check both correctness and
how many KMS calls a request costs.
"""

import threading
import time

import jwt
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa, utils

from auth_module.services.token_service import TokenService
from common_module.blocking_io import shutdown_blocking_io


def _new_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


class FakeKmsSigner:
    def __init__(self, private_key=None):
        self.private_key = private_key or _new_key()
        self.key_fetches = 0
        self.remote_verifies = 0
        self.sign_threads = []
        self.fail_fetch = False

    def sign(self, message: bytes, **_kwargs) -> bytes:
        self.sign_threads.append(threading.get_ident())
        return self.private_key.sign(
            message,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32),
            utils.Prehashed(hashes.SHA256()),
        )

    def verify(self, message: bytes, signature: bytes, **_kwargs) -> bool:
        self.remote_verifies += 1
        raise AssertionError('tokens must be verified locally, not with a KMS call')

    def get_public_key_pem(self, **_kwargs) -> bytes:
        self.key_fetches += 1
        if self.fail_fetch:
            raise RuntimeError('KMS unavailable')
        return self.private_key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )

    def rotate(self):
        self.private_key = _new_key()


def make_service(signer, **kwargs):
    return TokenService(
        signer,
        token_expiry=3600,
        temporary_token_expiry=600,
        app_env='test',
        issuer='https://floware.test',
        audience='https://floware.test',
        validation_issuers=['https://floware.test'],
        token_prefix='fc_',
        **kwargs,
    )


def make_token(service, **overrides):
    claims = dict(sub='a@b.c', user_id='u1', role_id='r1', payload={'session_id': 's1'})
    claims.update(overrides)
    return service.create_token(**claims)


@pytest.fixture(autouse=True)
def fresh_pools():
    yield
    shutdown_blocking_io()


@pytest.fixture
def signer():
    return FakeKmsSigner()


async def test_valid_token_decodes_without_remote_verify(signer):
    service = make_service(signer)

    decoded = await service.decode_token_async(make_token(service))

    assert decoded['session_id'] == 's1'
    assert decoded['user_id'] == 'u1'
    assert signer.remote_verifies == 0


async def test_key_is_fetched_once_for_many_requests(signer):
    service = make_service(signer)
    token = make_token(service)

    for _ in range(20):
        await service.decode_token_async(token)

    assert signer.key_fetches == 1


async def test_key_is_refetched_after_the_cache_expires(signer):
    service = make_service(signer, public_key_cache_seconds=0.05)
    token = make_token(service)

    await service.decode_token_async(token)
    time.sleep(0.1)
    await service.decode_token_async(token)

    assert signer.key_fetches == 2


async def test_zero_cache_fetches_the_key_on_every_request(signer):
    service = make_service(signer, public_key_cache_seconds=0)
    token = make_token(service)

    for _ in range(3):
        assert (await service.decode_token_async(token))['session_id'] == 's1'

    assert signer.key_fetches == 3


async def test_zero_cache_bad_signature_costs_no_extra_fetch(signer):
    service = make_service(signer, public_key_cache_seconds=0)
    forged = make_token(make_service(FakeKmsSigner()))

    assert await service.decode_token_async(forged) == {}
    assert signer.key_fetches == 1


async def test_forged_token_returns_empty_like_before(signer):
    """A bad signature used to make the KMS verify return False -> {}."""
    service = make_service(signer)
    forged = make_token(make_service(FakeKmsSigner()))

    assert await service.decode_token_async(forged) == {}


async def test_rotated_key_is_picked_up_from_a_new_token(signer):
    service = make_service(signer, public_key_refresh_min_seconds=0)
    await service.decode_token_async(make_token(service))  # caches the old key
    signer.rotate()

    decoded = await service.decode_token_async(make_token(service))

    assert decoded['session_id'] == 's1'
    assert signer.key_fetches == 2


async def test_forged_tokens_cause_at_most_one_refetch(signer):
    service = make_service(signer, public_key_refresh_min_seconds=60)
    await service.decode_token_async(make_token(service))
    service._key_fetched_at -= 120  # the cached key is old enough to refetch once
    forged = make_token(make_service(FakeKmsSigner()))

    results = [await service.decode_token_async(forged) for _ in range(100)]

    assert results == [{}] * 100
    assert signer.key_fetches == 2  # the first fetch plus one rotation check


async def test_expired_token_still_raises(signer):
    service = make_service(signer)
    token = make_token(service, expiry=-10)

    with pytest.raises(jwt.ExpiredSignatureError):
        await service.decode_token_async(token)


async def test_malformed_token_raises_invalid_token(signer):
    service = make_service(signer)

    with pytest.raises(jwt.InvalidTokenError, match='format'):
        await service.decode_token_async('not-a-jwt')


async def test_kms_failure_raises_invalid_token(signer):
    service = make_service(signer)
    token = make_token(service)
    signer.fail_fetch = True

    with pytest.raises(jwt.InvalidTokenError):
        await service.decode_token_async(token)


def test_sync_decode_uses_the_same_cache(signer):
    service = make_service(signer)
    token = make_token(service)

    assert service.decode_token(token)['session_id'] == 's1'
    assert service.decode_token(token)['session_id'] == 's1'
    assert signer.key_fetches == 1
    assert signer.remote_verifies == 0


async def test_create_token_async_signs_off_the_loop(signer):
    service = make_service(signer)

    token = await service.create_token_async(
        sub='a@b.c', user_id='u1', role_id='r1', payload={'session_id': 's9'}
    )

    assert signer.sign_threads and threading.get_ident() not in signer.sign_threads
    assert (await service.decode_token_async(token))['session_id'] == 's9'


def test_cache_settings_default_when_missing(signer):
    service = make_service(
        signer, public_key_cache_seconds=None, public_key_refresh_min_seconds=''
    )

    assert service.public_key_cache_seconds == 600
    assert service.public_key_refresh_min_seconds == 60


def test_negative_cache_setting_is_rejected(signer):
    with pytest.raises(ValueError):
        make_service(signer, public_key_cache_seconds='-1')
