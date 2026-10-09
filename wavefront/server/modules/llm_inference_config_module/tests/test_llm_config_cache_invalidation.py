"""LlmInferenceConfigService tells the injected invalidator about every write."""

import uuid
from unittest.mock import AsyncMock, Mock

import pytest

from llm_inference_config_module.services.llm_inference_config_service import (
    LlmInferenceConfigService,
)

CONFIG_ID = uuid.uuid4()


def make_record():
    record = Mock()
    record.id = CONFIG_ID
    record.to_dict.return_value = {'id': str(CONFIG_ID)}
    return record


@pytest.fixture
def invalidator():
    inv = Mock()
    inv.invalidate = AsyncMock(return_value=True)
    return inv


@pytest.fixture
def repository():
    repo = Mock()
    repo.create = AsyncMock(return_value=make_record())
    repo.find_one = AsyncMock(return_value=make_record())
    repo.find_one_and_update = AsyncMock(return_value=make_record())
    return repo


@pytest.fixture
def service(repository, invalidator):
    return LlmInferenceConfigService(repository, Mock(), invalidator)


async def test_create_invalidates(service, invalidator):
    await service.create_config(
        llm_model='gpt-4',
        display_name='GPT-4',
        api_key='k',
        type='openai',
        base_url='https://api.openai.com',
    )

    invalidator.invalidate.assert_awaited_once_with(
        'llm_inference_config', CONFIG_ID, 'create'
    )


async def test_update_invalidates(service, invalidator):
    await service.update_config(CONFIG_ID, display_name='renamed')

    invalidator.invalidate.assert_awaited_once_with(
        'llm_inference_config', CONFIG_ID, 'update'
    )


async def test_delete_invalidates(service, invalidator):
    assert await service.delete_config(CONFIG_ID) is True

    invalidator.invalidate.assert_awaited_once_with(
        'llm_inference_config', CONFIG_ID, 'delete'
    )


async def test_missing_config_is_not_invalidated(service, repository, invalidator):
    repository.find_one = AsyncMock(return_value=None)

    assert await service.update_config(CONFIG_ID, display_name='x') is None
    assert await service.delete_config(CONFIG_ID) is False

    invalidator.invalidate.assert_not_awaited()
