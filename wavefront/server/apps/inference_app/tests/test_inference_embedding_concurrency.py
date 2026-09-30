"""
Tests that image embedding stays off the event loop and that forward passes on
the shared models are serialised. The models are replaced with fakes, so no
weights are loaded.
"""

import asyncio
import base64
import io
import threading
import time
from unittest.mock import patch

import pytest

torch = pytest.importorskip('torch')

import httpx  # noqa: E402
from dependency_injector import providers  # noqa: E402
from PIL import Image  # noqa: E402

from inference_app.rate_limiter import SlidingWindowRateLimiter  # noqa: E402
from inference_app.service import image_embedding  # noqa: E402
from inference_app.service.image_embedding import ImageEmbedding  # noqa: E402


def png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new('RGB', (4, 4), color='red').save(buffer, format='PNG')
    return buffer.getvalue()


class BlockingEmbedding:
    """Stands in for ImageEmbedding; query_embed blocks until released."""

    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.finished = False

    def query_embed(self, image_content: bytes):
        self.started.set()
        # Bounded so the test fails rather than hangs if the call ever runs on
        # the event loop again.
        self.release.wait(timeout=5)
        self.finished = True
        return [{'clip': [1.0]}, {'dino': [1.0]}]


@pytest.fixture
def app_with_blocking_embedding():
    from inference_app import server

    fake = BlockingEmbedding()
    container = server.inference_app_container
    with (
        container.image_embedding.override(providers.Object(fake)),
        container.rate_limiter.override(providers.Object(SlidingWindowRateLimiter([]))),
    ):
        yield server.app, fake


async def test_health_check_responds_while_embedding_is_running(
    app_with_blocking_embedding,
):
    app, fake = app_with_blocking_embedding
    payload = {'image_data': base64.b64encode(png_bytes()).decode('ascii')}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url='http://test') as client:
        embed_request = asyncio.create_task(
            client.post('/inference/v1/query/embeddings', json=payload)
        )
        assert await asyncio.to_thread(fake.started.wait, 5)

        health = await client.get('/inference/v1/health')

        assert health.status_code == 200
        assert not fake.finished, 'health check waited for the embedding to finish'

        fake.release.set()
        response = await embed_request

    assert response.status_code == 200
    assert response.json()['data']['response'] == [{'clip': [1.0]}, {'dino': [1.0]}]


def make_service_with_fake_models(forward_seconds: float = 0.05):
    """An ImageEmbedding whose embedders are fakes that record how many
    forward passes run at the same time."""
    service = ImageEmbedding.__new__(ImageEmbedding)
    service.device = torch.device('cpu')
    service._model_lock = threading.Lock()

    counter_lock = threading.Lock()
    stats = {'active': 0, 'max_active': 0}

    def processor(images, return_tensors):
        count = len(images) if isinstance(images, list) else 1
        return {'pixel_values': torch.zeros(count, 3)}

    def extractor(inputs):
        with counter_lock:
            stats['active'] += 1
            stats['max_active'] = max(stats['max_active'], stats['active'])
        time.sleep(forward_seconds)
        with counter_lock:
            stats['active'] -= 1
        return torch.ones(inputs['pixel_values'].shape[0], 4)

    service.embedders = {
        name: {'processor': processor, 'model': None, 'extractor': extractor}
        for name in ('clip', 'dino')
    }
    return service, stats


def run_concurrently(fn, count: int):
    results = [None] * count

    def worker(index):
        results[index] = fn()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    return results


def test_concurrent_query_embed_calls_do_not_overlap_forward_passes():
    service, stats = make_service_with_fake_models()
    image = png_bytes()

    results = run_concurrently(lambda: service.query_embed(image), count=4)

    assert stats['max_active'] == 1
    for result in results:
        assert result == [{'clip': [0.5] * 4}, {'dino': [0.5] * 4}]


def test_concurrent_query_embed_batch_calls_do_not_overlap_forward_passes():
    service, stats = make_service_with_fake_models()
    batch = [png_bytes(), png_bytes()]

    results = run_concurrently(lambda: service.query_embed_batch(batch), count=4)

    assert stats['max_active'] == 1
    for result in results:
        assert result == [{'clip': [[0.5] * 4] * 2}, {'dino': [[0.5] * 4] * 2}]


@pytest.mark.parametrize('method', ['query_embed', 'query_embed_batch'])
def test_undecodable_image_raises_value_error_and_logs(method):
    service, stats = make_service_with_fake_models()
    payload = (
        b'not an image' if method == 'query_embed' else [png_bytes(), b'not an image']
    )

    with (
        patch.object(image_embedding, 'logger') as logger,
        pytest.raises(ValueError, match='(?i)failed to decode image'),
    ):
        getattr(service, method)(payload)

    logger.error.assert_called_once()
    assert stats['max_active'] == 0, 'model ran on an undecodable image'
