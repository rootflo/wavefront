"""SecretCipher: flag-off passthrough, flag-on strictness, masking and merging."""

import asyncio

import pytest

from common_module.feature.feature_flag import ENVELOPE_ENCRYPTION_ENABLED, FeatureFlags
from common_module.security.secret_cipher import (
    SECRET_MASK,
    SecretCipher,
    SecretModeMismatchError,
    UnencryptedSecretError,
)
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


def _enabled() -> SecretCipher:
    return SecretCipher(
        enabled=True, envelope_factory=lambda: EnvelopeCipher(FakeKms())
    )


def _disabled() -> SecretCipher:
    def never_called():
        raise AssertionError('KMS must not be built while encryption is disabled')

    return SecretCipher(enabled=False, envelope_factory=never_called)


# ---- flag off ---------------------------------------------------------------


def test_disabled_stores_and_reads_values_unchanged():
    cipher = _disabled()

    assert cipher.protect('sk-live') == 'sk-live'
    assert cipher.reveal('sk-live') == 'sk-live'
    assert cipher.protect_json({'k': 'v'}) == {'k': 'v'}
    assert cipher.reveal_json({'k': 'v'}) == {'k': 'v'}


def test_disabled_rejects_encrypted_values():
    token = _enabled().protect('sk-live')
    cipher = _disabled()

    with pytest.raises(SecretModeMismatchError):
        cipher.reveal(token)
    with pytest.raises(SecretModeMismatchError):
        cipher.reveal_json(token)


# ---- flag on ----------------------------------------------------------------


def test_enabled_round_trip():
    cipher = _enabled()

    stored = cipher.protect('sk-live')

    assert SecretCipher.is_encrypted(stored)
    assert cipher.reveal(stored) == 'sk-live'


def test_enabled_rejects_plaintext():
    cipher = _enabled()

    with pytest.raises(UnencryptedSecretError):
        cipher.reveal('sk-live')
    with pytest.raises(UnencryptedSecretError):
        cipher.reveal_json('sk-live')


def test_enabled_protect_never_passes_ciphertext_through():
    # A ciphertext copied from another record must not be stored as-is, or it
    # would decrypt to that record's secret wherever it is planted.
    cipher = _enabled()
    copied = cipher.protect('victim-key')

    stored = cipher.protect(copied)
    stored_json = cipher.protect_json(copied)

    assert stored != copied
    assert cipher.reveal(stored) == copied
    assert cipher.reveal_json(stored_json) == copied


def test_empty_values_pass_through_in_both_modes():
    for cipher in (_enabled(), _disabled()):
        assert cipher.protect(None) is None
        assert cipher.reveal(None) is None
        assert cipher.protect('') == ''
        assert cipher.protect_json(None) is None


def test_fields_keep_their_json_type():
    cipher = _enabled()
    config = {
        'host': 'db.local',
        'password': 'pw',
        'credentials_json': {'private_key': 'k', 'client_email': 'e'},
    }
    fields = ('password', 'credentials_json')

    stored = cipher.protect_fields(config, fields)

    assert stored['host'] == 'db.local'
    assert SecretCipher.is_encrypted(stored['password'])
    assert SecretCipher.is_encrypted(stored['credentials_json'])
    assert cipher.reveal_fields(stored, fields) == config


def test_fields_skip_missing_and_none():
    cipher = _enabled()

    stored = cipher.protect_fields({'password': None}, ('password', 'other'))

    assert stored == {'password': None}


# ---- masking and merging ------------------------------------------------------


def test_mask_fields():
    masked = SecretCipher.mask_fields(
        {'host': 'h', 'password': 'pw', 'token': '', 'key': None},
        ('password', 'token', 'key', 'absent'),
    )

    assert masked == {'host': 'h', 'password': SECRET_MASK, 'token': '', 'key': None}


def test_merge_masked_keeps_stored_for_sentinel_and_missing():
    stored = {'host': 'old', 'password': 'pw', 'api_token': 't'}
    incoming = {'host': 'new', 'password': SECRET_MASK}

    merged = SecretCipher.merge_masked(incoming, stored, ('password', 'api_token'))

    assert merged == {'host': 'new', 'password': 'pw', 'api_token': 't'}


def test_merge_masked_new_value_and_explicit_none():
    stored = {'password': 'pw', 'api_token': 't'}
    incoming = {'password': 'new-pw', 'api_token': None}

    merged = SecretCipher.merge_masked(incoming, stored, ('password', 'api_token'))

    assert merged == {'password': 'new-pw', 'api_token': None}


def test_merge_masked_sentinel_without_stored_value_is_dropped():
    merged = SecretCipher.merge_masked({'password': SECRET_MASK}, {}, ('password',))

    assert merged == {}


# ---- flag parsing -------------------------------------------------------------


def test_feature_flag_parses_envelope_encryption():
    on = FeatureFlags.from_config(
        {'feature_flags': {'envelope_encryption_enabled': 'true'}}
    )
    off = FeatureFlags.from_config({})

    assert on.enabled(ENVELOPE_ENCRYPTION_ENABLED)
    assert not off.enabled(ENVELOPE_ENCRYPTION_ENABLED)


# ---- async variants -------------------------------------------------------------


class _ThreadCounter:
    def __init__(self, monkeypatch):
        self.calls = 0
        real = asyncio.to_thread

        async def counting(func, *args, **kwargs):
            self.calls += 1
            return await real(func, *args, **kwargs)

        monkeypatch.setattr(
            'common_module.security.secret_cipher.asyncio.to_thread', counting
        )


async def test_areveal_offloads_only_when_kms_is_needed(monkeypatch):
    writer = _enabled()
    stored = writer.protect('sk-live')
    reader = SecretCipher(
        enabled=True, envelope_factory=lambda: EnvelopeCipher(FakeKms())
    )
    threads = _ThreadCounter(monkeypatch)

    assert await reader.areveal(stored) == 'sk-live'  # cold: KMS unwrap
    assert await reader.areveal(stored) == 'sk-live'  # warm: cached data key

    assert threads.calls == 1


async def test_areveal_fields_round_trip(monkeypatch):
    cipher = _enabled()
    threads = _ThreadCounter(monkeypatch)
    fields = ('password', 'credentials_json')
    config = {'host': 'h', 'password': 'pw', 'credentials_json': {'k': 'v'}}

    stored = await cipher.aprotect_fields(config, fields)

    assert await cipher.areveal_fields(stored, fields) == config
    assert threads.calls == 1  # the write; the read reuses cached data keys


async def test_async_variants_never_offload_when_disabled(monkeypatch):
    cipher = _disabled()
    threads = _ThreadCounter(monkeypatch)

    assert await cipher.aprotect('sk-live') == 'sk-live'
    assert await cipher.areveal('sk-live') == 'sk-live'
    assert await cipher.areveal_fields({'password': 'pw'}, ('password',)) == {
        'password': 'pw'
    }
    assert threads.calls == 0
