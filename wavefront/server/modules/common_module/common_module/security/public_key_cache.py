"""Cache for a KMS public key used to verify our own JWTs locally.

Floware and floconsole sign tokens with a KMS key. Verifying used to call KMS
twice per request (a remote verify plus a public-key fetch) on the event loop.
The public key changes only on rotation, so this caches it and the token
services verify signatures locally with it.

- ``cache_seconds``: how long a fetched key is reused. 0 disables the cache: the
  key is fetched for every verification (still off the event loop), which gives
  instant revocation when a key is disabled.
- ``refresh_min_seconds``: tokens carry no key id, so a token whose signature
  doesn't match the cached key may mean the key was rotated. That triggers a
  refetch, but at most one per ``refresh_min_seconds``, so forged tokens can't
  turn into one KMS call each.

Fetches run on the ``kms`` blocking-I/O pool and only one runs at a time: a
burst of requests on an expired cache causes one KMS call, not one per request.
"""

from __future__ import annotations

import math
import threading
import time
from typing import Callable, Optional, TypeVar, Union

from common_module.blocking_io import run_in_pool

Key = Union[bytes, str]
T = TypeVar('T')


class PublicKeyUnavailableError(RuntimeError):
    """The public key could not be fetched (KMS down or unreachable).

    Deliberately not a JWT error: the token may be perfectly valid, so callers
    must answer 503 (try again), never 401 (which clients treat as logged out).
    """


def seconds_setting(value: Union[float, str, None], default: float) -> float:
    """A non-negative number of seconds from config; missing means the default."""
    if value is None or value == '':
        return float(default)
    seconds = float(value)
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError(
            f'Expected a finite, non-negative number of seconds, got {value!r}'
        )
    return seconds


class PublicKeyCache:
    def __init__(
        self,
        fetch: Callable[[], Key],
        *,
        cache_seconds: Union[float, str, None] = None,
        refresh_min_seconds: Union[float, str, None] = None,
    ):
        """
        Args:
            fetch: Blocking call that returns the PEM public key (e.g. from KMS).
            cache_seconds: Default 600. 0 disables the cache.
            refresh_min_seconds: Default 60.
        """
        self._fetch = fetch
        self.cache_seconds = seconds_setting(cache_seconds, 600)
        self.refresh_min_seconds = seconds_setting(refresh_min_seconds, 60)
        self._key: Optional[Key] = None
        self._fetched_at = float('-inf')
        self._state_lock = threading.Lock()  # guards _key and _fetched_at
        self._fetch_lock = threading.Lock()  # one fetch at a time

    # -- verification flows ------------------------------------------------------

    def verify(self, decode: Callable[[Key], Optional[T]]) -> Optional[T]:
        """Blocking: ``decode(key)``, retried once with a refetched key if it
        returns None (signature mismatch) and the key may have been rotated."""
        key = self.get()
        result = decode(key)
        if result is None and self._refetch_allowed():
            new_key = self.refetch_if_rotated(key)
            if new_key is not None:
                result = decode(new_key)
        return result

    async def averify(self, decode: Callable[[Key], Optional[T]]) -> Optional[T]:
        """Async ``verify``: key fetches go to the ``kms`` pool; decoding runs inline."""
        key = self.cached()
        if key is None:
            key = await run_in_pool('kms', self.get)
        result = decode(key)
        if result is None and self._refetch_allowed():
            new_key = await run_in_pool('kms', self.refetch_if_rotated, key)
            if new_key is not None:
                result = decode(new_key)
        return result

    # -- key access ----------------------------------------------------------------

    def cached(self) -> Optional[Key]:
        """The cached key if it is still fresh; never blocks."""
        if self.cache_seconds <= 0:
            return None
        with self._state_lock:
            if (
                self._key is not None
                and time.monotonic() - self._fetched_at < self.cache_seconds
            ):
                return self._key
        return None

    def get(self) -> Key:
        """The cached key, fetching it first if missing or stale. Blocking."""
        with self._fetch_lock:
            key = self.cached()
            if key is not None:
                return key
            return self._fetch_and_store()

    def refetch_if_rotated(self, key_used: Key) -> Optional[Key]:
        """Refetch after a signature mismatch, rate-limited. Blocking.

        Returns a different key to retry with, or None.
        """
        with self._fetch_lock:
            with self._state_lock:
                current, fetched_at = self._key, self._fetched_at
            if current is not None and current != key_used:
                return current  # another request already refreshed it
            if time.monotonic() - fetched_at < self.refresh_min_seconds:
                return None
            new_key = self._fetch_and_store()
        return new_key if new_key != key_used else None

    def _refetch_allowed(self) -> bool:
        # With the cache off, the key was fetched for this very request already.
        return self.cache_seconds > 0

    def _fetch_and_store(self) -> Key:
        try:
            key = self._fetch()
        except PublicKeyUnavailableError:
            raise
        except Exception as e:
            raise PublicKeyUnavailableError(
                f'Could not fetch the token public key: {type(e).__name__}: {e}'
            ) from e
        with self._state_lock:
            self._key = key
            self._fetched_at = time.monotonic()
        return key
