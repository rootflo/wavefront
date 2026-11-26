"""Message processor tool details load each YAML from storage off the event loop."""

import threading
from unittest.mock import AsyncMock, Mock

import pytest
import yaml

from common_module.blocking_io import BlockingPoolBusyError, shutdown_blocking_io
from tools_module.message_processor import provider as provider_module
from tools_module.message_processor.provider import (
    MessageProcessorToolDetailsProvider,
)

PROCESSOR_YAML = yaml.safe_dump(
    {
        'type': 'javascript',
        'description': 'Echo the input',
        'function': {'code': 'export default (input) => input'},
        'input_schema': {
            'required': ['message'],
            'properties': {'message': {'type': 'string'}},
        },
    }
)


@pytest.fixture(autouse=True)
def fresh_pools():
    yield
    shutdown_blocking_io()


def make_provider(read_file):
    processor = Mock(id='mp-1', source='echo.yaml', description='')
    processor.name = 'echo'
    return MessageProcessorToolDetailsProvider(
        message_processor_repository=AsyncMock(
            find=AsyncMock(return_value=[processor])
        ),
        cloud_storage_manager=Mock(read_file=read_file),
        message_processor_bucket_name='bucket',
    )


async def test_yaml_reads_run_off_the_loop():
    threads = []

    def read_file(_bucket, _key):
        threads.append(threading.get_ident())
        return PROCESSOR_YAML.encode()

    details = await make_provider(read_file).get_tool_details({})

    assert [d.name for d in details] == ['echo']
    assert details[0].required == ['message']
    assert threads and threading.get_ident() not in threads


async def test_busy_storage_pool_is_raised_not_skipped(monkeypatch):
    """Overload must reach the client as a 503, not as a missing tool."""

    async def busy(*_args, **_kwargs):
        raise BlockingPoolBusyError('storage', 10.0)

    monkeypatch.setattr(provider_module, 'run_in_pool', busy)

    with pytest.raises(BlockingPoolBusyError):
        await make_provider(Mock()).get_tool_details({})
