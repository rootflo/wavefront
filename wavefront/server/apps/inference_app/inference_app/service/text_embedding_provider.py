"""The optional text embedding model's load state, kept free of torch so the
app can start (in mock mode) where torch isn't installed."""

import threading
from typing import Any, Callable, Optional

from common_module.log.logger import logger


class TextEmbeddingUnavailable(Exception):
    """The text embedding model is disabled, still loading, or failed to load."""


class TextEmbeddingProvider:
    """Holds the optional BGE-M3 model and where its loading stands.

    The model loads in the background so the server (and the image endpoints)
    come up without waiting for it, and a missing or broken model never stops
    the server: requests just get TextEmbeddingUnavailable until it's ready.
    """

    DISABLED = 'disabled'
    LOADING = 'loading'
    READY = 'ready'
    FAILED = 'failed'

    def __init__(self):
        self.status = self.DISABLED
        self.error: Optional[str] = None
        self._model: Optional[Any] = None

    def load(self, loader: Callable[[], Any]) -> None:
        """Run `loader` (blocking) and record the outcome. Never raises."""
        self.status = self.LOADING
        try:
            model = loader()
        except Exception as err:
            self.error = str(err)
            self.status = self.FAILED
            logger.error(
                f'BGE-M3 text embedding model failed to load; text embeddings '
                f'are unavailable: {err}',
                exc_info=True,
            )
            return
        self._model = model
        self.status = self.READY
        logger.info('BGE-M3 text embedding model ready')

    def start_loading(self, loader: Callable[[], Any]) -> threading.Thread:
        """Load on a daemon thread, so neither startup nor shutdown waits for
        it (a model sync from cloud storage can take minutes)."""
        self.status = self.LOADING
        thread = threading.Thread(
            target=self.load, args=(loader,), name='bge-m3-loader', daemon=True
        )
        thread.start()
        return thread

    def get(self) -> Any:
        if self.status == self.READY and self._model is not None:
            return self._model
        if self.status == self.LOADING:
            raise TextEmbeddingUnavailable('Text embedding model is still loading')
        if self.status == self.FAILED:
            raise TextEmbeddingUnavailable(
                f'Text embedding model failed to load: {self.error}'
            )
        raise TextEmbeddingUnavailable(
            'Text embeddings are not enabled (BGE_M3_MODEL_URI is not set)'
        )
