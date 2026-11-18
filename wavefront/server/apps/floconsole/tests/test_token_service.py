"""Floconsole TokenService: local verification with the cached KMS public key.

A fake signer does real RSA-PSS signing (the scheme KMS uses) and counts the
"remote" calls, so the tests check results and how many KMS calls they cost.
"""

import threading

import jwt
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa, utils

from common_module.blocking_io import shutdown_blocking_io
from floconsole.services.token_service import TokenService
from floconsole.utils.password_utils import (
    hash_password,
    hash_password_async,
    verify_password_async,
)


class FakeKmsSigner:
    def __init__(self):
        self.private_key = rsa.generate_private_key(
            public_exponent=65537, key_size=2048
        )
        self.key_fetches = 0
        self.sign_threads = []

    def sign(self, message: bytes, **_kwargs) -> bytes:
        self.sign_threads.append(threading.get_ident())
        return self.private_key.sign(
            message,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32),
            utils.Prehashed(hashes.SHA256()),
        )

    def verify(self, *_args, **_kwargs) -> bool:
        raise AssertionError('tokens must be verified locally, not with a KMS call')

    def get_public_key_pem(self, **_kwargs) -> bytes:
        self.key_fetches += 1
        return self.private_key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )


def make_service(signer, **kwargs):
    return TokenService(
        signer,
        token_expiry=3600,
        temporary_token_expiry=300,
        app_env='test',
        token_prefix='fc_',
        issuer='https://console.test',
        audience='https://console.test',
        **kwargs,
    )


def make_token(service):
    return service.create_token(
        sub='a@b.c', user_id='u1', role_id='r1', payload={'session_id': 's1'}
    )


@pytest.fixture(autouse=True)
def fresh_pools():
    yield
    shutdown_blocking_io()


@pytest.fixture
def signer():
    return FakeKmsSigner()


async def test_valid_token_decodes_locally_and_reuses_the_key(signer):
    service = make_service(signer)
    token = make_token(service)

    for _ in range(5):
        assert (await service.decode_token_async(token))['session_id'] == 's1'

    assert signer.key_fetches == 1


async def test_missing_prefix_is_still_a_value_error(signer):
    service = make_service(signer)
    token = make_token(service)

    with pytest.raises(ValueError, match='missing prefix'):
        await service.decode_token_async(token[len('fc_') :])


async def test_forged_token_returns_empty(signer):
    service = make_service(signer)
    forged = make_token(make_service(FakeKmsSigner()))

    assert await service.decode_token_async(forged) == {}


async def test_zero_cache_fetches_every_time(signer):
    service = make_service(signer, public_key_cache_seconds=0)
    token = make_token(service)

    await service.decode_token_async(token)
    await service.decode_token_async(token)

    assert signer.key_fetches == 2


def test_sync_decode_still_works(signer):
    service = make_service(signer)

    assert service.decode_token(make_token(service))['user_id'] == 'u1'


async def test_expired_token_raises(signer):
    service = make_service(signer)
    token = service.create_token(
        sub='a@b.c',
        user_id='u1',
        role_id='r1',
        payload={'session_id': 's1'},
        expiry=-10,
    )

    with pytest.raises(jwt.ExpiredSignatureError):
        await service.decode_token_async(token)


async def test_create_token_async_signs_off_the_loop(signer):
    service = make_service(signer)

    token = await service.create_token_async(
        sub='a@b.c', user_id='u1', role_id='r1', payload={'session_id': 's9'}
    )

    assert token.startswith('fc_')
    assert threading.get_ident() not in signer.sign_threads
    assert (await service.decode_token_async(token))['session_id'] == 's9'


async def test_async_bcrypt_helpers_round_trip():
    hashed = await hash_password_async('pw')

    assert await verify_password_async('pw', hashed) is True
    assert await verify_password_async('pw', hash_password('other')) is False
