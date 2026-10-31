"""Authenticator client secrets: stored through SecretCipher, masked in responses,
merged on update, and revealed only for the AuthenticatorFactory."""

import json
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from common_module.security.secret_cipher import (
    SECRET_MASK,
    SecretCipher,
    UnencryptedSecretError,
)
from db_repo_module.models.authenticator import Authenticator
from flo_cloud._types import FloCipher
from flo_cloud.envelope import EnvelopeCipher
from plugins_module.services import authenticator_services as services
from plugins_module.utils.authenticator_helper import (
    AUTHENTICATOR_SECRET_FIELDS,
    get_authenticator_secret_fields,
)

AUTH_ID = uuid.UUID('22222222-2222-2222-2222-222222222222')
GOOGLE_CONFIG = {
    'client_id': 'cid',
    'client_secret': 'google-secret',
    'redirect_uri': 'https://app.example.com/cb',
    'client_redirect_success_url': 'https://app.example.com/ok',
    'client_redirect_failure_url': 'https://app.example.com/fail',
    'scopes': ['openid'],
}
FIELDS = ('client_secret',)


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


@pytest.fixture(params=[False, True], ids=['flag_off', 'flag_on'])
def cipher(request):
    return _cipher(request.param)


@pytest.fixture
def factory():
    factory = MagicMock()
    with patch.object(services, 'get_authenticator_factory', return_value=factory):
        yield factory


def _row(config: dict, auth_type: str = 'google_oauth', is_enabled=True):
    now = datetime(2026, 1, 1)
    return Authenticator(
        auth_id=AUTH_ID,
        auth_name='google',
        auth_type=auth_type,
        auth_desc=None,
        config=config,
        is_enabled=is_enabled,
        is_deleted=False,
        created_at=now,
        updated_at=now,
    )


def _repository(row=None, existing_by_name=None):
    repository = MagicMock()

    async def find_one(**kwargs):
        return existing_by_name if 'auth_name' in kwargs else row

    repository.find_one = AsyncMock(side_effect=find_one)
    repository.create = AsyncMock(side_effect=lambda **kw: _row(kw['config']))

    async def update(filters, refresh, **kw):
        return _row(kw.get('config', row.config if row else {}))

    repository.find_one_and_update = AsyncMock(side_effect=update)
    return repository


def _assert_stored(cipher, value, plaintext):
    if cipher.enabled:
        assert SecretCipher.is_encrypted(value)
        assert cipher.reveal_json(value) == plaintext
    else:
        assert value == plaintext


def _assert_no_secret(payload, *secrets):
    text = json.dumps(payload)
    assert 'enc:v1:' not in text
    for secret in secrets:
        assert secret not in text


class TestSecretFieldMap:
    @pytest.mark.parametrize(
        'auth_type', ['google_oauth', 'microsoft_oauth', 'microsoft_adfs']
    )
    def test_oauth_types_protect_the_client_secret(self, auth_type):
        assert get_authenticator_secret_fields(auth_type) == FIELDS

    def test_email_password_has_none(self):
        assert get_authenticator_secret_fields('email_password') == ()
        assert 'email_password' not in AUTHENTICATOR_SECRET_FIELDS

    def test_accepts_the_enum(self):
        from authenticator import AuthenticatorType

        assert (
            get_authenticator_secret_fields(AuthenticatorType.MICROSOFT_ADFS) == FIELDS
        )


class TestCreate:
    async def test_validates_plaintext_and_stores_protected(self, cipher, factory):
        repository = _repository()

        result = await services.create_authenticator_config(
            auth_name='google',
            auth_type='google_oauth',
            auth_desc=None,
            config=GOOGLE_CONFIG,
            authenticator_repository=repository,
            secret_cipher=cipher,
        )

        validated = factory.validate_config.call_args.args[1]
        assert validated['client_secret'] == 'google-secret'
        stored = repository.create.call_args.kwargs['config']
        _assert_stored(cipher, stored['client_secret'], 'google-secret')
        assert factory.get_authenticator.call_args.args[2] == GOOGLE_CONFIG
        assert result['config']['client_secret'] == SECRET_MASK
        _assert_no_secret(result, 'google-secret')

    async def test_reactivating_a_deleted_one_stores_protected(self, cipher, factory):
        deleted = _row({})
        deleted.is_deleted = True
        repository = _repository(existing_by_name=deleted)

        await services.create_authenticator_config(
            auth_name='google',
            auth_type='google_oauth',
            auth_desc=None,
            config=GOOGLE_CONFIG,
            authenticator_repository=repository,
            secret_cipher=cipher,
        )

        stored = repository.find_one_and_update.call_args.kwargs['config']
        _assert_stored(cipher, stored['client_secret'], 'google-secret')


class TestUpdate:
    async def test_masked_secret_keeps_the_stored_one(self, cipher, factory):
        row = _row(cipher.protect_fields(GOOGLE_CONFIG, FIELDS))
        repository = _repository(row)
        edited = {**GOOGLE_CONFIG, 'client_id': 'cid-2', 'client_secret': SECRET_MASK}

        result = await services.update_authenticator_config(
            auth_id=AUTH_ID,
            config=edited,
            authenticator_repository=repository,
            secret_cipher=cipher,
        )

        expected = {**GOOGLE_CONFIG, 'client_id': 'cid-2'}
        assert factory.validate_config.call_args.args[1] == expected
        saved = repository.find_one_and_update.call_args.kwargs['config']
        _assert_stored(cipher, saved['client_secret'], 'google-secret')
        # The cached instance is rebuilt from the merged plaintext config
        factory.update_authenticator.assert_called_once()
        assert factory.update_authenticator.call_args.args[0] == str(AUTH_ID)
        assert factory.update_authenticator.call_args.args[2] == expected
        assert result['config']['client_secret'] == SECRET_MASK
        _assert_no_secret(result, 'google-secret')

    async def test_a_new_secret_replaces_the_stored_one(self, cipher, factory):
        row = _row(cipher.protect_fields(GOOGLE_CONFIG, FIELDS))
        repository = _repository(row)

        await services.update_authenticator_config(
            auth_id=AUTH_ID,
            config={**GOOGLE_CONFIG, 'client_secret': 'rotated'},
            authenticator_repository=repository,
            secret_cipher=cipher,
        )

        saved = repository.find_one_and_update.call_args.kwargs['config']
        _assert_stored(cipher, saved['client_secret'], 'rotated')
        assert factory.update_authenticator.call_args.args[2]['client_secret'] == (
            'rotated'
        )


class TestReads:
    async def test_get_config_is_masked(self, cipher):
        row = _row(cipher.protect_fields(GOOGLE_CONFIG, FIELDS))
        result = await services.get_authenticator_config(AUTH_ID, _repository(row))
        assert result['config']['client_secret'] == SECRET_MASK
        assert result['config']['client_id'] == 'cid'
        _assert_no_secret(result, 'google-secret')

    async def test_with_config_reveals_for_the_factory_only(self, cipher, factory):
        row = _row(cipher.protect_fields(GOOGLE_CONFIG, FIELDS))

        instance, config_data = await services.get_authenticator_with_config(
            AUTH_ID, _repository(row), cipher
        )

        assert instance is factory.get_authenticator.return_value
        assert factory.get_authenticator.call_args.args[2] == GOOGLE_CONFIG
        assert config_data['config']['client_secret'] == SECRET_MASK
        assert config_data['config']['client_redirect_failure_url'] == (
            'https://app.example.com/fail'
        )

    async def test_with_config_disabled_builds_no_instance(self, cipher, factory):
        row = _row(cipher.protect_fields(GOOGLE_CONFIG, FIELDS), is_enabled=False)

        instance, config_data = await services.get_authenticator_with_config(
            AUTH_ID, _repository(row), cipher
        )

        assert instance is None
        assert config_data['is_enabled'] is False
        factory.get_authenticator.assert_not_called()

    async def test_with_config_not_found(self, cipher, factory):
        assert await services.get_authenticator_with_config(
            AUTH_ID, _repository(None), cipher
        ) == (None, None)

    async def test_instance_reveals_for_the_factory(self, cipher, factory):
        row = _row(cipher.protect_fields(GOOGLE_CONFIG, FIELDS))

        instance = await services.get_authenticator_instance(
            AUTH_ID, _repository(row), cipher
        )

        assert instance is factory.get_authenticator.return_value
        assert factory.get_authenticator.call_args.args[2] == GOOGLE_CONFIG

    async def test_flag_on_rejects_a_plaintext_secret(self, factory):
        with pytest.raises(UnencryptedSecretError):
            await services.get_authenticator_instance(
                AUTH_ID, _repository(_row(GOOGLE_CONFIG)), _cipher(True)
            )

    async def test_email_password_config_is_untouched(self, cipher, factory):
        config = {'session_timeout': 3600}
        row = _row(config, auth_type='email_password')

        await services.get_authenticator_instance(AUTH_ID, _repository(row), cipher)

        assert factory.get_authenticator.call_args.args[2] == config
