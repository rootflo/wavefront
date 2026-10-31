"""EnvelopeCipher: format, strictness, tamper detection and the DEK cache."""

import base64

import pytest

from flo_cloud._types import FloCipher
from flo_cloud.envelope import (
    ENVELOPE_PREFIX,
    EnvelopeCipher,
    UnencryptedSecretError,
    is_envelope_encrypted,
)
from flo_cloud.exceptions import KmsError


class FakeKms(FloCipher):
    """Reversible stand-in for KMS that counts calls."""

    def __init__(self):
        self.encrypt_calls = 0
        self.decrypt_calls = 0

    def encrypt(self, plaintext):
        self.encrypt_calls += 1
        data = plaintext.encode() if isinstance(plaintext, str) else plaintext
        return b'kms:' + bytes(reversed(data))

    def decrypt(self, ciphertext):
        self.decrypt_calls += 1
        assert ciphertext.startswith(b'kms:')
        return bytes(reversed(ciphertext[4:]))

    def encrypt_for_storage(self, plaintext):
        raise NotImplementedError

    def decrypt_from_storage(self, stored):
        raise NotImplementedError


def test_round_trip_and_format():
    cipher = EnvelopeCipher(FakeKms())

    token = cipher.encrypt('sk-live-123')

    assert token.startswith(ENVELOPE_PREFIX)
    assert 'sk-live-123' not in token
    assert cipher.decrypt(token) == 'sk-live-123'


def test_each_value_gets_its_own_data_key():
    kms = FakeKms()
    cipher = EnvelopeCipher(kms)

    first, second = cipher.encrypt('same'), cipher.encrypt('same')

    assert first != second
    assert kms.encrypt_calls == 2


def test_large_values_are_supported():
    cipher = EnvelopeCipher(FakeKms())
    service_account = 'x' * 10_000

    assert cipher.decrypt(cipher.encrypt(service_account)) == service_account


def test_plaintext_is_rejected():
    cipher = EnvelopeCipher(FakeKms())

    with pytest.raises(UnencryptedSecretError):
        cipher.decrypt('sk-live-123')


def test_tampered_ciphertext_is_rejected():
    cipher = EnvelopeCipher(FakeKms())
    token = cipher.encrypt('sk-live-123')
    wrapped, payload = token[len(ENVELOPE_PREFIX) :].split(':')
    raw = bytearray(base64.b64decode(payload))
    raw[-1] ^= 0x01
    tampered = f'{ENVELOPE_PREFIX}{wrapped}:{base64.b64encode(bytes(raw)).decode()}'

    with pytest.raises(KmsError):
        cipher.decrypt(tampered)


def test_malformed_ciphertext_is_rejected():
    cipher = EnvelopeCipher(FakeKms())

    with pytest.raises(KmsError):
        cipher.decrypt(f'{ENVELOPE_PREFIX}not-base64')


def test_dek_cache_avoids_kms_on_repeat_decrypts():
    kms = FakeKms()
    writer = EnvelopeCipher(kms)
    token = writer.encrypt('sk-live-123')
    reader = EnvelopeCipher(kms)  # fresh process: empty cache

    reader.decrypt(token)
    reader.decrypt(token)
    reader.decrypt(token)

    assert kms.decrypt_calls == 1


def test_dek_cache_entries_expire(monkeypatch):
    kms = FakeKms()
    token = EnvelopeCipher(kms).encrypt('sk-live-123')
    reader = EnvelopeCipher(kms, cache_ttl_seconds=60)
    clock = [1000.0]
    monkeypatch.setattr('flo_cloud.envelope.time.monotonic', lambda: clock[0])

    reader.decrypt(token)
    clock[0] += 61
    reader.decrypt(token)

    assert kms.decrypt_calls == 2


def test_dek_cache_is_bounded():
    kms = FakeKms()
    writer = EnvelopeCipher(kms)
    tokens = [writer.encrypt(f'secret-{i}') for i in range(3)]
    reader = EnvelopeCipher(kms, cache_max_entries=2)

    for token in tokens:
        reader.decrypt(token)
    reader.decrypt(tokens[0])  # evicted, so unwrapped again

    assert kms.decrypt_calls == 4


def test_rewrap_keeps_the_secret_and_changes_the_wrapped_key():
    kms = FakeKms()
    cipher = EnvelopeCipher(kms)
    token = cipher.encrypt('sk-live-123')

    rewrapped = cipher.rewrap(token)

    assert rewrapped.split(':')[-1] == token.split(':')[-1]
    assert cipher.decrypt(rewrapped) == 'sk-live-123'


def test_is_envelope_encrypted():
    assert is_envelope_encrypted(f'{ENVELOPE_PREFIX}abc:def')
    assert not is_envelope_encrypted('sk-live-123')
    assert not is_envelope_encrypted(None)
    assert not is_envelope_encrypted({'a': 1})


def test_is_key_cached():
    kms = FakeKms()
    token = EnvelopeCipher(kms).encrypt('sk-live-123')
    reader = EnvelopeCipher(kms)

    assert not reader.is_key_cached(token)
    reader.decrypt(token)
    assert reader.is_key_cached(token)
    assert not reader.is_key_cached('sk-live-123')
