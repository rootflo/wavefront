"""HMAC secret generation: stored through SecretCipher, plaintext returned once."""

import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from auth_module.controllers import hmac_controller
from common_module.response_formatter import ResponseFormatter
from common_module.security.secret_cipher import SecretCipher
from db_repo_module.models.auth_secrets import AuthSecrets
from flo_cloud._types import FloCipher
from flo_cloud.envelope import EnvelopeCipher


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


def _cipher(enabled: bool) -> SecretCipher:
    return SecretCipher(
        enabled=enabled, envelope_factory=lambda: EnvelopeCipher(FakeKms())
    )


def _repository():
    repository = MagicMock()
    repository.create = AsyncMock(
        side_effect=lambda **kw: AuthSecrets(
            client_key=kw['client_key'],
            client_secret=kw['client_secret'],
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
        )
    )
    return repository


@pytest.mark.parametrize('enabled', [False, True], ids=['flag_off', 'flag_on'])
async def test_stores_protected_and_returns_plaintext_once(enabled):
    cipher = _cipher(enabled)
    repository = _repository()
    request = SimpleNamespace(
        state=SimpleNamespace(session=SimpleNamespace(role_id='admin'))
    )

    with patch.object(hmac_controller, 'check_is_admin', AsyncMock(return_value=True)):
        response = await hmac_controller.generate_hmac_secret(
            request=request,
            auth_secrets_repository=repository,
            response_formatter=ResponseFormatter(),
            secret_cipher=cipher,
        )

    assert response.status_code == 201
    returned = json.loads(response.body)['data']['client_secret']
    assert len(returned) == 64
    stored = repository.create.call_args.kwargs['client_secret']
    assert SecretCipher.is_encrypted(stored) is enabled
    assert cipher.reveal(stored) == returned


def test_to_dict_never_carries_the_secret():
    row = AuthSecrets(
        client_key='hmac_k',
        client_secret='s',
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )
    assert 'client_secret' not in row.to_dict()
