"""Config services tell the injected invalidator about every write.

The invalidator is a constructor dependency, so these tests hand in a mock and
check what the services ask it to invalidate; nothing touches the network.
"""

import uuid
from unittest.mock import AsyncMock, Mock

import pytest

from voice_agents_module.services.stt_config_service import SttConfigService
from voice_agents_module.services.tts_config_service import TtsConfigService

CONFIG_ID = uuid.uuid4()


def make_record(config_id=CONFIG_ID):
    record = Mock()
    record.id = config_id
    record.to_dict.return_value = {'id': str(config_id)}
    return record


@pytest.fixture
def invalidator():
    return Mock(invalidate=AsyncMock(return_value=True))


@pytest.fixture
def repository():
    repo = Mock()
    repo.create = AsyncMock(return_value=make_record())
    repo.find_one = AsyncMock(return_value=make_record())
    repo.find_one_and_update = AsyncMock(return_value=make_record())
    return repo


@pytest.fixture(
    params=[('tts_config', TtsConfigService), ('stt_config', SttConfigService)]
)
def service_case(request, repository, invalidator):
    config_type, service_cls = request.param
    service = service_cls(repository, Mock(), invalidator)
    return config_type, service


class TestVoiceConfigServices:
    async def test_create_invalidates(self, service_case, invalidator):
        config_type, service = service_case

        await service.create_config(display_name='x', provider='p', api_key='k')

        invalidator.invalidate.assert_awaited_once_with(
            config_type, CONFIG_ID, 'create'
        )

    async def test_update_invalidates(self, service_case, invalidator):
        config_type, service = service_case

        await service.update_config(CONFIG_ID, display_name='y')

        invalidator.invalidate.assert_awaited_once_with(
            config_type, CONFIG_ID, 'update'
        )

    async def test_delete_invalidates(self, service_case, invalidator):
        config_type, service = service_case

        assert await service.delete_config(CONFIG_ID) is True

        invalidator.invalidate.assert_awaited_once_with(
            config_type, CONFIG_ID, 'delete'
        )

    async def test_missing_config_is_not_invalidated(
        self, service_case, repository, invalidator
    ):
        _, service = service_case
        repository.find_one = AsyncMock(return_value=None)

        assert await service.update_config(CONFIG_ID, display_name='y') is None
        assert await service.delete_config(CONFIG_ID) is False

        invalidator.invalidate.assert_not_awaited()
