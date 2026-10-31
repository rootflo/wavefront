"""Secrets table, reference resolution in the registry, validation, masking and the admin API."""

import json
import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import yaml
from fastapi import HTTPException

from api_services_module.config.registry import ServiceRegistry
from api_services_module.core.manager import ApiServicesManager
from api_services_module.core.proxy import ApiProxy
from api_services_module.models.pipeline import PipelineContext
from api_services_module.pipeline.builder import PipelineBuilder
from api_services_module.secrets import secret_controller
from api_services_module.secrets.secret_controller import (
    CreateSecretPayload,
    UpdateSecretPayload,
)
from api_services_module.secrets.secret_store_service import (
    SecretNotFound,
    SecretStoreService,
)
from common_module.response_formatter import ResponseFormatter
from common_module.security.secret_cipher import SECRET_MASK, SecretCipher
from db_repo_module.models.secret import Secret
from flo_cloud._types import FloCipher
from flo_cloud.envelope import ENVELOPE_PREFIX, EnvelopeCipher


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
    if enabled:
        return SecretCipher(
            enabled=True, envelope_factory=lambda: EnvelopeCipher(FakeKms())
        )
    return SecretCipher(enabled=False)


class FakeSecretRepository:
    """In-memory stand-in for SQLAlchemyRepository[Secret]."""

    def __init__(self):
        self.rows = {}

    async def create(self, **kwargs):
        now = datetime(2026, 10, 28, 12, 0, 0)
        secret = Secret(id=uuid.uuid4(), created_at=now, updated_at=now, **kwargs)
        self.rows[secret.id] = secret
        return secret

    async def find_one(self, **filters):
        for secret in self.rows.values():
            if all(getattr(secret, key) == value for key, value in filters.items()):
                return secret
        return None

    async def find(self, limit=100, order_by=None, **filters):
        result = []
        for secret in self.rows.values():
            matches = True
            for key, value in filters.items():
                current = getattr(secret, key)
                if isinstance(value, list):
                    matches = matches and current in value
                else:
                    matches = matches and current == value
            if matches:
                result.append(secret)
        if order_by:
            result.sort(key=lambda s: getattr(s, order_by))
        return result[:limit]

    async def find_one_and_update(self, filters, *, refresh=False, **update_data):
        secret = await self.find_one(**filters)
        if not secret:
            return None
        for key, value in update_data.items():
            setattr(secret, key, value)
        return secret

    async def delete_all(self, **filters):
        secret = await self.find_one(**filters)
        if secret:
            del self.rows[secret.id]
        return True


def _store(enabled: bool = False):
    repository = FakeSecretRepository()
    return SecretStoreService(repository, _cipher(enabled)), repository


def _service_yaml(service_id='acme', auth=None, api_headers=None):
    api = {
        'id': 'get-user',
        'path': '/users/{id}',
        'backend_path': '/users/{id}',
        'method': 'GET',
    }
    if api_headers:
        api['additional_headers'] = api_headers
    return yaml.safe_dump(
        {
            'service': {
                'id': service_id,
                'base_url': 'https://acme.test',
                'auth': auth
                or {
                    'id': 'acme-auth',
                    'type': 'bearer',
                    'token': '${secrets.ACME_TOKEN}',
                },
                'apis': [api],
            }
        }
    )


class FakeApiServicesManager:
    def __init__(self, yaml_by_id):
        self.yaml_by_id = dict(yaml_by_id)

    async def get_all_api_services(self):
        return [SimpleNamespace(id=service_id) for service_id in self.yaml_by_id]

    async def get_api_service(self, id):
        return SimpleNamespace(id=id) if id in self.yaml_by_id else None

    def fetch_service_def(self, service):
        return self.yaml_by_id[service.id]

    async def create_api_service(self, id, service_def_yaml):
        self.yaml_by_id[id] = service_def_yaml

    async def update_api_service(self, id, service_def_yaml):
        self.yaml_by_id[id] = service_def_yaml
        return True


# ---- SecretStoreService ---------------------------------------------------------


@pytest.mark.parametrize('enabled', [False, True])
async def test_store_round_trip_in_both_modes(enabled):
    store, repository = _store(enabled)

    created = await store.create('ACME_TOKEN', 'sk-live', 'Acme API token')

    stored = next(iter(repository.rows.values())).value
    if enabled:
        assert stored.startswith(ENVELOPE_PREFIX)
        assert 'sk-live' not in stored
    else:
        assert stored == 'sk-live'
    assert 'value' not in created
    assert created['has_value'] is True
    assert created['name'] == 'ACME_TOKEN'
    assert await store.resolve(['ACME_TOKEN']) == {'ACME_TOKEN': 'sk-live'}


@pytest.mark.parametrize('enabled', [False, True])
async def test_store_rotate_and_metadata_reads(enabled):
    store, repository = _store(enabled)
    created = await store.create('ACME_TOKEN', 'old', None)
    secret_id = uuid.UUID(created['id'])

    await store.update(secret_id, value='new')
    updated = await store.update(secret_id, description='rotated')

    assert updated['description'] == 'rotated'
    assert await store.resolve({'ACME_TOKEN'}) == {'ACME_TOKEN': 'new'}
    for item in [await store.get(secret_id), *(await store.list())]:
        assert 'value' not in item
        assert 'new' not in json.dumps(item)


@pytest.mark.parametrize(
    'name', ['acme_token', '1TOKEN', '_TOKEN', 'ACME-TOKEN', 'ACME TOKEN', '', 'A\n']
)
async def test_store_rejects_invalid_names(name):
    store, _ = _store()

    with pytest.raises(ValueError, match='upper snake case'):
        await store.create(name, 'value', None)


async def test_store_rejects_duplicates_and_empty_values():
    store, _ = _store()
    await store.create('ACME_TOKEN', 'value', None)

    with pytest.raises(ValueError, match='already exists'):
        await store.create('ACME_TOKEN', 'other', None)
    with pytest.raises(ValueError, match='must not be empty'):
        await store.create('OTHER', '', None)


async def test_store_resolve_unknown_names_and_missing():
    store, _ = _store()
    await store.create('KNOWN', 'v', None)

    with pytest.raises(ValueError, match='Unknown secret: NOPE'):
        await store.resolve(['KNOWN', 'NOPE'])
    assert await store.missing(['NOPE', 'KNOWN', 'ALSO_NOPE']) == ['ALSO_NOPE', 'NOPE']
    assert await store.resolve([]) == {}


async def test_store_delete_and_not_found():
    store, repository = _store()
    created = await store.create('ACME_TOKEN', 'v', None)
    secret_id = uuid.UUID(created['id'])

    await store.delete(secret_id)

    assert repository.rows == {}
    with pytest.raises(SecretNotFound):
        await store.get(secret_id)


# ---- registry ----------------------------------------------------------------------


async def test_registry_resolves_execution_copy_and_keeps_definition():
    store, _ = _store(enabled=True)
    await store.create('ACME_TOKEN', 'sk-live', None)
    await store.create('ACME_HEADER', 'h-live', None)
    manager = FakeApiServicesManager(
        {
            'acme': _service_yaml(
                api_headers={'Authorization': 'Bearer ${secrets.ACME_HEADER}'}
            )
        }
    )
    registry = ServiceRegistry(manager, secret_store=store)

    await registry.load_from_db()

    execution = registry.get_service('acme')
    assert execution.auth.token == 'sk-live'
    assert execution.apis[0].additional_headers == {'Authorization': 'Bearer h-live'}
    definition = registry.get_service_definition('acme')
    assert definition.auth.token == '${secrets.ACME_TOKEN}'
    assert registry.services_referencing('ACME_TOKEN') == ['acme']
    assert registry.services_referencing('ACME_HEADER') == ['acme']

    # the pipeline authenticates with the resolved value
    pipeline = PipelineBuilder.build_auth_pipeline(execution)
    context = PipelineContext(
        service_id='acme', api_id='get-user', method='POST', path='/x'
    )
    context = await pipeline.execute(context)
    assert context.auth_headers['Authorization'] == 'Bearer sk-live'


async def test_registry_skips_only_the_service_with_a_missing_secret():
    store, _ = _store()
    await store.create('ACME_TOKEN', 'sk-live', None)
    manager = FakeApiServicesManager(
        {
            'acme': _service_yaml(),
            'broken': _service_yaml(
                'broken',
                auth={'id': 'a', 'type': 'bearer', 'token': '${secrets.GONE}'},
            ),
        }
    )
    registry = ServiceRegistry(manager, secret_store=store)

    await registry.load_from_db()

    assert registry.get_service('acme') is not None
    assert registry.get_service('broken') is None
    # still listed for read paths and indexed, so it can be fixed
    assert 'broken' in registry.get_definition_ids()
    assert registry.services_referencing('GONE') == ['broken']


async def test_registry_reverse_index_follows_reload_and_removal():
    store, _ = _store()
    await store.create('ACME_TOKEN', 'one', None)
    await store.create('OTHER_TOKEN', 'two', None)
    manager = FakeApiServicesManager({'acme': _service_yaml()})
    registry = ServiceRegistry(manager, secret_store=store)
    await registry.load_from_db()

    manager.yaml_by_id['acme'] = _service_yaml(
        auth={'id': 'a', 'type': 'bearer', 'token': '${secrets.OTHER_TOKEN}'}
    )
    await registry.reload_service('acme')

    assert registry.services_referencing('ACME_TOKEN') == []
    assert registry.services_referencing('OTHER_TOKEN') == ['acme']
    assert registry.get_service('acme').auth.token == 'two'

    registry.deregister_service('acme')
    assert registry.services_referencing('OTHER_TOKEN') == []


async def test_registry_reload_picks_up_a_rotated_value():
    store, _ = _store(enabled=True)
    created = await store.create('ACME_TOKEN', 'old', None)
    manager = FakeApiServicesManager({'acme': _service_yaml()})
    registry = ServiceRegistry(manager, secret_store=store)
    proxy = ApiProxy(registry, manager, Mock(), secret_store=store)
    await registry.load_from_db()

    await store.update(uuid.UUID(created['id']), value='new')
    await proxy.reload_service('acme')

    assert registry.get_service('acme').auth.token == 'new'
    handler = proxy.auth_manager.get_auth_handler('acme')
    assert handler.auth_config.token == 'new'


# ---- validation on create / update -------------------------------------------------


async def _proxy(enabled: bool, yaml_by_id=None, secrets=('ACME_TOKEN',)):
    store, _ = _store(enabled)
    for name in secrets:
        await store.create(name, f'{name.lower()}-value', None)
    manager = FakeApiServicesManager(yaml_by_id or {})
    registry = ServiceRegistry(manager, secret_store=store)
    await registry.load_from_db()
    publisher = Mock()
    return ApiProxy(registry, manager, publisher, secret_store=store), manager


@pytest.mark.parametrize('enabled', [False, True])
async def test_create_rejects_unknown_reference(enabled):
    proxy, manager = await _proxy(enabled)
    service_yaml = _service_yaml(
        auth={'id': 'a', 'type': 'bearer', 'token': '${secrets.NOT_THERE}'}
    )

    with pytest.raises(HTTPException) as error:
        await proxy.create_api_services(service_yaml)

    assert error.value.status_code == 400
    assert error.value.detail == 'Unknown secret: NOT_THERE'
    assert manager.yaml_by_id == {}


async def test_create_rejects_literal_when_encryption_enabled():
    proxy, manager = await _proxy(enabled=True)
    service_yaml = _service_yaml(api_headers={'X-Api-Key': 'literal-key'})

    with pytest.raises(HTTPException) as error:
        await proxy.create_api_services(service_yaml)

    assert error.value.status_code == 400
    assert error.value.detail == (
        'Use ${secrets.NAME} instead of a literal value for '
        'service.apis[0].additional_headers.X-Api-Key'
    )
    assert manager.yaml_by_id == {}


async def test_create_accepts_literal_when_encryption_disabled():
    proxy, manager = await _proxy(enabled=False)
    service_yaml = _service_yaml(
        auth={'id': 'a', 'type': 'bearer', 'token': 'literal-token'},
        api_headers={'X-Api-Key': 'literal-key'},
    )

    await proxy.create_api_services(service_yaml)

    assert manager.yaml_by_id['acme'] == service_yaml
    assert proxy.service_registry.get_service('acme').auth.token == 'literal-token'


async def test_create_with_reference_stores_reference_and_resolves():
    proxy, manager = await _proxy(enabled=True)

    await proxy.create_api_services(_service_yaml())

    assert '${secrets.ACME_TOKEN}' in manager.yaml_by_id['acme']
    assert 'acme_token-value' not in manager.yaml_by_id['acme']
    assert proxy.service_registry.get_service('acme').auth.token == 'acme_token-value'


async def test_update_keeps_stored_literal_sent_back_masked():
    original = _service_yaml(
        auth={'id': 'a', 'type': 'bearer', 'token': 'literal-token'}
    )
    proxy, manager = await _proxy(enabled=False, yaml_by_id={'acme': original})

    edited = _service_yaml(auth={'id': 'a', 'type': 'bearer', 'token': SECRET_MASK})
    await proxy.update_api_services('acme', edited)

    stored = yaml.safe_load(manager.yaml_by_id['acme'])
    assert stored['service']['auth']['token'] == 'literal-token'


async def test_update_rejects_literal_when_encryption_enabled():
    proxy, manager = await _proxy(enabled=True, yaml_by_id={'acme': _service_yaml()})

    with pytest.raises(HTTPException) as error:
        await proxy.update_api_services(
            'acme',
            _service_yaml(auth={'id': 'a', 'type': 'bearer', 'token': 'literal-token'}),
        )

    assert error.value.status_code == 400
    assert 'service.auth.token' in error.value.detail


# ---- read paths --------------------------------------------------------------------


async def test_read_paths_show_references_and_mask_literals():
    yaml_by_id = {
        'acme': _service_yaml(api_headers={'Authorization': 'Bearer literal'}),
        'legacy': _service_yaml(
            'legacy',
            auth={
                'id': 'b',
                'type': 'basic',
                'username': 'user',
                'password': 'hunter2',
                'additional_headers': {'X-Client-Id': 'client-1'},
            },
        ),
    }
    proxy, _ = await _proxy(enabled=False, yaml_by_id=yaml_by_id)

    acme = proxy.get_service_info('acme')
    assert acme['auth'].token == '${secrets.ACME_TOKEN}'
    assert acme['apis'][0]['additional_headers'] == {'Authorization': SECRET_MASK}

    listed = {s['service_id']: s for s in proxy.get_all_services_info()['services']}
    legacy = listed['legacy']
    assert legacy['auth'].password == SECRET_MASK
    assert legacy['auth'].username == 'user'
    assert legacy['auth'].additional_headers == {'X-Client-Id': 'client-1'}

    serialized = json.dumps(
        proxy.get_all_services_info()['services'],
        default=lambda o: getattr(o, '__dict__', str(o)),
    )
    for plaintext in ('acme_token-value', 'hunter2', 'Bearer literal'):
        assert plaintext not in serialized


# ---- manager ---------------------------------------------------------------------


async def test_delete_api_service_removes_cache_key():
    cache_manager = Mock()
    manager = ApiServicesManager(
        api_services_repository=AsyncMock(),
        cloud_storage_manager=Mock(),
        cache_manager=cache_manager,
        config={'storage': {'application_bucket': 'bucket'}},
    )

    await manager.delete_api_service('acme')

    cache_manager.remove.assert_called_once_with('api_services/acme.yaml')


# ---- admin API ---------------------------------------------------------------------


@pytest.fixture
def admin(monkeypatch):
    is_admin = AsyncMock(return_value=True)
    monkeypatch.setattr(secret_controller, 'check_is_admin', is_admin)
    return is_admin


def _request():
    return SimpleNamespace(state=SimpleNamespace(session=SimpleNamespace(role_id='r')))


def _body(response):
    return json.loads(response.body)


async def _controller_setup():
    store, _ = _store(enabled=True)
    manager = FakeApiServicesManager(
        {'acme': _service_yaml(), 'beta': _service_yaml('beta')}
    )
    registry = ServiceRegistry(manager, secret_store=store)
    created = await store.create('ACME_TOKEN', 'old', None)
    await registry.load_from_db()
    return store, registry, uuid.UUID(created['id'])


async def test_delete_is_refused_while_referenced(admin):
    store, registry, secret_id = await _controller_setup()

    response = await secret_controller.delete_secret(
        _request(),
        secret_id,
        response_formatter=ResponseFormatter(),
        secret_store=store,
        service_registry=registry,
    )

    assert response.status_code == 409
    assert _body(response)['data'] == {'service_ids': ['acme', 'beta']}
    assert await store.get(secret_id)


async def test_delete_unreferenced_secret(admin):
    store, registry, _ = await _controller_setup()
    unused = await store.create('UNUSED', 'v', None)

    response = await secret_controller.delete_secret(
        _request(),
        uuid.UUID(unused['id']),
        response_formatter=ResponseFormatter(),
        secret_store=store,
        service_registry=registry,
    )

    assert response.status_code == 200
    assert await store.missing(['UNUSED']) == ['UNUSED']


async def test_rotate_publishes_update_for_each_referencing_service(admin):
    store, registry, secret_id = await _controller_setup()
    publisher = Mock()

    response = await secret_controller.update_secret(
        _request(),
        secret_id,
        UpdateSecretPayload(value='new'),
        response_formatter=ResponseFormatter(),
        secret_store=store,
        service_registry=registry,
        api_change_publisher=publisher,
    )

    assert response.status_code == 200
    assert 'new' not in response.body.decode()
    published = [call.args[0] for call in publisher.publish_message.call_args_list]
    assert [(m.service_id, m.operation) for m in published] == [
        ('acme', 'update'),
        ('beta', 'update'),
    ]
    assert await store.resolve(['ACME_TOKEN']) == {'ACME_TOKEN': 'new'}


async def test_description_edit_does_not_reload(admin):
    store, registry, secret_id = await _controller_setup()
    publisher = Mock()

    await secret_controller.update_secret(
        _request(),
        secret_id,
        UpdateSecretPayload(description='docs'),
        response_formatter=ResponseFormatter(),
        secret_store=store,
        service_registry=registry,
        api_change_publisher=publisher,
    )

    publisher.publish_message.assert_not_called()


async def test_create_returns_metadata_and_400_on_bad_name(admin):
    store, registry, _ = await _controller_setup()

    created = await secret_controller.create_secret(
        _request(),
        CreateSecretPayload(name='NEW_TOKEN', value='sk-new'),
        response_formatter=ResponseFormatter(),
        secret_store=store,
        service_registry=registry,
        api_change_publisher=Mock(),
    )
    bad = await secret_controller.create_secret(
        _request(),
        CreateSecretPayload(name='new-token', value='sk-new'),
        response_formatter=ResponseFormatter(),
        secret_store=store,
        service_registry=registry,
        api_change_publisher=Mock(),
    )

    assert created.status_code == 201
    assert 'sk-new' not in created.body.decode()
    assert _body(created)['data']['secret']['has_value'] is True
    assert bad.status_code == 400


async def test_non_admin_is_forbidden(monkeypatch):
    monkeypatch.setattr(
        secret_controller, 'check_is_admin', AsyncMock(return_value=False)
    )
    store, _ = _store()

    response = await secret_controller.list_secrets(
        _request(), response_formatter=ResponseFormatter(), secret_store=store
    )

    assert response.status_code == 403
