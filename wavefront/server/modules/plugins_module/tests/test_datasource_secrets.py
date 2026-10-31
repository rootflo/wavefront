"""Datasource secrets: stored through SecretCipher, masked in responses, merged on edit.

Every case runs with encryption off and on. Off, stored values are plaintext as
before; on, they are `enc:v1:` ciphertext. Responses are masked either way.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from datasource import (
    DATASOURCE_SECRET_FIELDS,
    BigQueryConfig,
    DataSourceType,
    PostgresConfig,
    get_datasource_secret_fields,
)
from datasource.file_storage.config import S3FileStorageConfig

from common_module.common_container import CommonContainer
from common_module.response_formatter import ResponseFormatter
from common_module.security.secret_cipher import (
    SECRET_MASK,
    SecretCipher,
    SecretModeMismatchError,
    UnencryptedSecretError,
)
from db_repo_module.models.datasource import Datasource
from dependency_injector import providers
from flo_cloud._types import FloCipher
from flo_cloud.envelope import EnvelopeCipher
from plugins_module.controllers import datasource_controller as controller
from plugins_module.plugins_container import PluginsContainer
from plugins_module.services import datasource_services
from plugins_module.utils.helper import AddDatasourcePayload, UpdateDatasourcePayload

DATASOURCE_ID = '11111111-1111-1111-1111-111111111111'
PG_CONFIG = {
    'host': 'db.example.com',
    'port': 5432,
    'database': 'orders',
    'user': 'app',
    'password': 'pg-secret',
}
S3_CONFIG = {
    'bucket_name': 'bkt',
    'aws_access_key_id': 'AKIA',
    'aws_secret_access_key': 's3-secret',
}
SA_KEY = {'type': 'service_account', 'private_key': 'bq-secret'}
BQ_CONFIG = {
    'project_id': 'p',
    'dataset_id': 'd',
    'location': 'US',
    'credentials_json': SA_KEY,
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


def _cipher(enabled: bool) -> SecretCipher:
    return SecretCipher(
        enabled=enabled, envelope_factory=lambda: EnvelopeCipher(FakeKms())
    )


@pytest.fixture(params=[False, True], ids=['flag_off', 'flag_on'])
def cipher(request):
    return _cipher(request.param)


@pytest.fixture
def formatter():
    return ResponseFormatter()


@pytest.fixture
def request_obj():
    return SimpleNamespace(state=SimpleNamespace(session=SimpleNamespace(role_id='r')))


@pytest.fixture(autouse=True)
def _admin_and_cache():
    with (
        patch.object(controller, 'check_is_admin', AsyncMock(return_value=True)),
        patch.object(controller, 'invalidate_datasources_cache'),
    ):
        yield


@pytest.fixture
def connection_test():
    with patch.object(
        controller, '_test_datasource_connection', AsyncMock(return_value=True)
    ) as mock:
        yield mock


def _row(type_: str, config: dict) -> Datasource:
    return Datasource(
        id=DATASOURCE_ID, name='ds', description=None, type=type_, config=config
    )


def _repository(row: Datasource | None = None) -> MagicMock:
    repository = MagicMock()
    repository.find_one = AsyncMock(return_value=row)
    repository.find = AsyncMock(return_value=[row] if row else [])
    repository.create = AsyncMock(
        side_effect=lambda **kw: _row(kw['type'], kw['config'])
    )

    async def update(filters, refresh, **kw):
        return _row(kw.get('type', row.type), kw.get('config', row.config))

    repository.find_one_and_update = AsyncMock(side_effect=update)
    return repository


def _body(response):
    return json.loads(response.body)['data']


def _assert_no_secret(payload, *secrets):
    text = json.dumps(payload)
    assert 'enc:v1:' not in text
    for secret in secrets:
        assert secret not in text


def _assert_stored(cipher: SecretCipher, value, plaintext):
    if cipher.enabled:
        assert SecretCipher.is_encrypted(value)
        assert cipher.reveal_json(value) == plaintext
    else:
        assert value == plaintext


class TestSecretFieldMap:
    def test_every_mapped_type_is_a_datasource_type(self):
        assert all(isinstance(t, DataSourceType) for t in DATASOURCE_SECRET_FIELDS)

    def test_lookup_by_string_and_enum(self):
        assert get_datasource_secret_fields('postgres') == ('password',)
        assert get_datasource_secret_fields(DataSourceType.GCP_BIGQUERY) == (
            'credentials_json',
            'credentials_path',
        )

    @pytest.mark.parametrize('type_', ['nope', None, 'redis'])
    def test_unknown_or_unmapped_type_has_none(self, type_):
        assert get_datasource_secret_fields(type_) == ()


class TestCreate:
    async def test_tests_with_plaintext_and_stores_protected(
        self, cipher, formatter, request_obj, connection_test
    ):
        repository = _repository()
        response = await controller.add_datasource(
            request=request_obj,
            add_datasource_payload=AddDatasourcePayload(
                name='ds', type='postgres', config=json.dumps(PG_CONFIG)
            ),
            response_formatter=formatter,
            datasource_repository=repository,
            cache_manager=MagicMock(),
            secret_cipher=cipher,
        )

        assert response.status_code == 201
        tested_config = connection_test.call_args.args[1]
        assert isinstance(tested_config, PostgresConfig)
        assert tested_config.password == 'pg-secret'
        stored = repository.create.call_args.kwargs['config']
        _assert_stored(cipher, stored['password'], 'pg-secret')
        assert stored['host'] == 'db.example.com'
        _assert_no_secret(_body(response), 'pg-secret')

    async def test_dict_valued_secret_keeps_its_type(
        self, cipher, formatter, request_obj, connection_test
    ):
        repository = _repository()
        await controller.add_datasource(
            request=request_obj,
            add_datasource_payload=AddDatasourcePayload(
                name='ds', type='gcp_bigquery', config=json.dumps(BQ_CONFIG)
            ),
            response_formatter=formatter,
            datasource_repository=repository,
            cache_manager=MagicMock(),
            secret_cipher=cipher,
        )

        stored = repository.create.call_args.kwargs['config']
        _assert_stored(cipher, stored['credentials_json'], SA_KEY)


class TestUpdate:
    async def _update(self, cipher, formatter, request_obj, row, payload):
        repository = _repository(row)
        response = await controller.update_datasource(
            request=request_obj,
            datasource_id=DATASOURCE_ID,
            update_datasource_payload=payload,
            response_formatter=formatter,
            datasource_repository=repository,
            cache_manager=MagicMock(),
            secret_cipher=cipher,
        )
        return response, repository

    async def test_masked_secret_keeps_the_stored_one(
        self, cipher, formatter, request_obj, connection_test
    ):
        row = _row('postgres', cipher.protect_fields(PG_CONFIG, ('password',)))
        edited = {**PG_CONFIG, 'host': 'new.example.com', 'password': SECRET_MASK}

        response, repository = await self._update(
            cipher,
            formatter,
            request_obj,
            row,
            UpdateDatasourcePayload(config=json.dumps(edited)),
        )

        assert response.status_code == 200
        tested_config = connection_test.call_args.args[1]
        assert tested_config.password == 'pg-secret'
        assert tested_config.host == 'new.example.com'
        saved = repository.find_one_and_update.call_args.kwargs['config']
        _assert_stored(cipher, saved['password'], 'pg-secret')
        data = _body(response)
        assert data['datasource']['config']['password'] == SECRET_MASK
        assert data['datasource']['config']['host'] == 'new.example.com'
        _assert_no_secret(data, 'pg-secret')

    async def test_a_new_secret_replaces_the_stored_one(
        self, cipher, formatter, request_obj, connection_test
    ):
        row = _row('postgres', cipher.protect_fields(PG_CONFIG, ('password',)))
        edited = {**PG_CONFIG, 'password': 'rotated'}

        _, repository = await self._update(
            cipher,
            formatter,
            request_obj,
            row,
            UpdateDatasourcePayload(config=json.dumps(edited)),
        )

        assert connection_test.call_args.args[1].password == 'rotated'
        saved = repository.find_one_and_update.call_args.kwargs['config']
        _assert_stored(cipher, saved['password'], 'rotated')

    async def test_file_storage_resent_masked_is_not_a_change(
        self, cipher, formatter, request_obj, connection_test
    ):
        row = _row(
            'aws_s3', cipher.protect_fields(S3_CONFIG, ('aws_secret_access_key',))
        )
        resent = {**S3_CONFIG, 'aws_secret_access_key': SECRET_MASK}

        response, repository = await self._update(
            cipher,
            formatter,
            request_obj,
            row,
            UpdateDatasourcePayload(name='renamed', config=json.dumps(resent)),
        )

        assert response.status_code == 200
        connection_test.assert_not_called()
        assert 'config' not in repository.find_one_and_update.call_args.kwargs
        _assert_no_secret(_body(response), 's3-secret')

    async def test_file_storage_changed_secret_is_refused(
        self, cipher, formatter, request_obj, connection_test
    ):
        row = _row(
            'aws_s3', cipher.protect_fields(S3_CONFIG, ('aws_secret_access_key',))
        )
        changed = {**S3_CONFIG, 'aws_secret_access_key': 'other'}

        response, repository = await self._update(
            cipher,
            formatter,
            request_obj,
            row,
            UpdateDatasourcePayload(config=json.dumps(changed)),
        )

        assert response.status_code == 400
        repository.find_one_and_update.assert_not_called()

    async def test_name_only_update_does_not_touch_the_secret(
        self, cipher, formatter, request_obj, connection_test
    ):
        row = _row('postgres', cipher.protect_fields(PG_CONFIG, ('password',)))

        response, repository = await self._update(
            cipher, formatter, request_obj, row, UpdateDatasourcePayload(name='n')
        )

        assert response.status_code == 200
        assert repository.find_one_and_update.call_args.kwargs == {
            'filters': {'id': DATASOURCE_ID},
            'refresh': True,
            'name': 'n',
        }


class TestResponsesAreMasked:
    async def test_list(self, cipher, formatter, request_obj):
        row = _row(
            'gcp_bigquery', cipher.protect_fields(BQ_CONFIG, ('credentials_json',))
        )
        response = await controller.get_datasources(
            request=request_obj,
            response_formatter=formatter,
            datasource_repository=_repository(row),
        )
        [listed] = _body(response)['datasources']
        assert listed['config']['credentials_json'] == SECRET_MASK
        assert listed['config']['project_id'] == 'p'
        _assert_no_secret(listed, 'bq-secret')

    async def test_get(self, cipher, formatter, request_obj):
        row = _row('postgres', cipher.protect_fields(PG_CONFIG, ('password',)))
        response = await controller.get_datasource(
            request=request_obj,
            datasource_id=DATASOURCE_ID,
            response_formatter=formatter,
            datasource_repository=_repository(row),
        )
        data = _body(response)
        assert data['config']['password'] == SECRET_MASK
        _assert_no_secret(data, 'pg-secret')


class TestRuntimeReader:
    async def test_reveals_before_building_the_config(self, cipher):
        row = _row('postgres', cipher.protect_fields(PG_CONFIG, ('password',)))
        type_, config = await datasource_services.get_datasource_config(
            DATASOURCE_ID, datasource_repository=_repository(row), secret_cipher=cipher
        )
        assert type_ == DataSourceType.POSTGRES
        assert config.password == 'pg-secret'

    async def test_reveals_dict_valued_secrets(self, cipher):
        row = _row(
            'gcp_bigquery', cipher.protect_fields(BQ_CONFIG, ('credentials_json',))
        )
        _, config = await datasource_services.get_datasource_config(
            DATASOURCE_ID, datasource_repository=_repository(row), secret_cipher=cipher
        )
        assert isinstance(config, BigQueryConfig)
        assert config.credentials_json == SA_KEY

    async def test_reveals_file_storage_secrets(self, cipher):
        row = _row(
            'aws_s3', cipher.protect_fields(S3_CONFIG, ('aws_secret_access_key',))
        )
        _, config = await datasource_services.get_datasource_config(
            DATASOURCE_ID, datasource_repository=_repository(row), secret_cipher=cipher
        )
        assert isinstance(config, S3FileStorageConfig)
        assert config.aws_secret_access_key == 's3-secret'

    async def test_flag_on_rejects_a_plaintext_secret(self):
        row = _row('postgres', PG_CONFIG)
        with pytest.raises(UnencryptedSecretError):
            await datasource_services.get_datasource_config(
                DATASOURCE_ID,
                datasource_repository=_repository(row),
                secret_cipher=_cipher(True),
            )

    async def test_flag_off_rejects_an_encrypted_secret(self):
        row = _row('postgres', _cipher(True).protect_fields(PG_CONFIG, ('password',)))
        with pytest.raises(SecretModeMismatchError):
            await datasource_services.get_datasource_config(
                DATASOURCE_ID,
                datasource_repository=_repository(row),
                secret_cipher=_cipher(False),
            )

    async def test_unwired_caller_gets_the_cipher_injected(self):
        """Scheduled jobs import the function and pass only the repository."""
        from_import = datasource_services.get_datasource_config
        cipher = _cipher(True)
        row = _row('postgres', cipher.protect_fields(PG_CONFIG, ('password',)))
        common = CommonContainer()
        common.secret_cipher.override(providers.Object(cipher))
        plugins = PluginsContainer()
        common.wire(modules=[datasource_services])
        plugins.wire(modules=[datasource_services])
        try:
            _, config = await from_import(
                datasource_id=DATASOURCE_ID, datasource_repository=_repository(row)
            )
        finally:
            plugins.unwire()
            common.unwire()
        assert config.password == 'pg-secret'
