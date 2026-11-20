"""ImageService: uploads run on the storage pool, and overload stays a 503."""

import io
import threading
from unittest.mock import Mock

import pytest
from PIL import Image

from common_module.blocking_io import BlockingPoolBusyError, shutdown_blocking_io
from gold_module.services import image_service as module
from gold_module.services.image_service import ImageService


@pytest.fixture(autouse=True)
def fresh_pools():
    yield
    shutdown_blocking_io()


def jpeg_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new('RGB', (4, 4), 'red').save(buffer, format='JPEG')
    return buffer.getvalue()


class Storage:
    def __init__(self):
        self.calls = []

    def save_small_file(self, data, bucket, key, content_type=None):
        self.calls.append((key, content_type, threading.get_ident()))


def make_service(storage):
    queue = Mock()
    queue.add_message.return_value = 'msg-1'
    return ImageService('bucket', storage, queue), queue


async def test_save_image_uploads_off_the_loop():
    storage = Storage()
    service, _ = make_service(storage)

    await service.save_image(jpeg_bytes(), 'a.jpg')

    [(key, content_type, thread)] = storage.calls
    assert key == 'historical_data/a.jpg'
    assert content_type == 'image/jpeg'
    assert thread != threading.get_ident()


async def test_process_image_uploads_image_and_metadata_off_the_loop():
    storage = Storage()
    service, queue = make_service(storage)

    result = await service.process_image(jpeg_bytes(), {'item_id': 'item-7'})

    assert result == {'status': 'success', 'message_id': 'msg-1'}
    assert [(key, ctype) for key, ctype, _ in storage.calls] == [
        ('item-7', 'image/jpeg'),
        ('gold_image_metadata/item-7.json', 'application/json'),
    ]
    assert threading.get_ident() not in [thread for *_, thread in storage.calls]
    assert queue.add_message.call_args[0][0]['key'] == 'item-7'


async def test_process_image_publishes_off_the_loop():
    """Brokers wait on the network, so the publish must not run on the loop."""
    service, queue = make_service(Storage())
    threads = []
    queue.add_message.side_effect = lambda _m: threads.append(threading.get_ident())

    await service.process_image(jpeg_bytes(), {'item_id': 'item-7'})

    assert threads and threads[0] != threading.get_ident()


async def test_process_image_lets_a_busy_pool_through(monkeypatch):
    """Overload must reach the client as a 503, not be wrapped as a failure."""

    async def busy(*_args, **_kwargs):
        raise BlockingPoolBusyError('storage', 10.0)

    monkeypatch.setattr(module, 'run_in_pool', busy)
    service, queue = make_service(Storage())

    with pytest.raises(BlockingPoolBusyError):
        await service.process_image(jpeg_bytes(), {'item_id': 'item-7'})

    queue.add_message.assert_not_called()


async def test_invalid_image_is_rejected_before_upload():
    storage = Storage()
    service, _ = make_service(storage)

    with pytest.raises(Exception, match='Invalid image data'):
        await service.process_image(b'not an image', {})

    assert storage.calls == []


async def test_image_decoding_runs_off_the_loop(monkeypatch):
    service, _ = make_service(Storage())
    threads = []
    real = service._validate_image_sync

    def recording(data):
        threads.append(threading.get_ident())
        return real(data)

    monkeypatch.setattr(service, '_validate_image_sync', recording)

    await service.save_image(jpeg_bytes(), 'a.jpg')

    assert threads and threads[0] != threading.get_ident()
