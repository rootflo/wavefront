"""Lightweight profiler for flo_ai.

This module provides a simple, zero-cost-when-disabled profiler that:

* Writes a human-readable flow log to a file with indentation that reflects
  call-nesting (works correctly with asyncio thanks to ``contextvars``).
* Emits a summary at process exit listing every instrumented section sorted
  by total time spent, with call count and average duration.

The profiler is disabled by default. Enable it either by calling
:func:`enable_profiling` explicitly, or by setting the ``FLO_AI_PROFILE``
environment variable to a file path::

    FLO_AI_PROFILE=profile.log python examples/azure_llm_example.py

Environment variables
---------------------
``FLO_AI_PROFILE``
    Path to the output file. When set, profiling is enabled automatically on
    import and the summary is written on process exit.
``FLO_AI_PROFILE_CONSOLE``
    When set to a truthy value (``1``, ``true``, ``yes``), each enter/exit
    line is also mirrored to the ``flo_ai`` logger at INFO level.
"""

from __future__ import annotations

import atexit
import contextvars
import functools
import os
import threading
import time
from collections import defaultdict
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

__all__ = [
    'enable_profiling',
    'disable_profiling',
    'is_enabled',
    'profile_async',
    'profile_sync',
    'aprofile',
    'profile',
    'record',
    'write_summary',
]


_enabled: bool = False
_log_path: Optional[Path] = None
_file_handle: Optional[Any] = None
_lock = threading.Lock()
_mirror_console: bool = False

_depth: contextvars.ContextVar[int] = contextvars.ContextVar(
    'flo_ai_profile_depth', default=0
)

_totals: Dict[str, List[float]] = defaultdict(list)
_process_start: float = time.perf_counter()


def _truthy(val: Optional[str]) -> bool:
    if not val:
        return False
    return val.strip().lower() in {'1', 'true', 'yes', 'on'}


def enable_profiling(
    log_file: str | os.PathLike[str] = 'flo_ai_profile.log',
    mirror_console: bool = False,
) -> Path:
    """Enable the profiler and direct output to ``log_file``.

    Safe to call multiple times; subsequent calls reopen the file.
    """
    global _enabled, _log_path, _file_handle, _mirror_console, _process_start

    disable_profiling()

    path = Path(log_file).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    _file_handle = open(path, 'w', buffering=1, encoding='utf-8')
    _log_path = path
    _mirror_console = mirror_console
    _enabled = True
    _process_start = time.perf_counter()

    header = (
        f"=== flo_ai profiler started at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n"
        f"Output: {path}\n"
    )
    _file_handle.write(header)

    atexit.register(write_summary)
    return path


def disable_profiling() -> None:
    global _enabled, _file_handle, _log_path
    _enabled = False
    if _file_handle is not None:
        try:
            _file_handle.flush()
            _file_handle.close()
        except Exception:
            pass
    _file_handle = None
    _log_path = None
    _totals.clear()


def is_enabled() -> bool:
    return _enabled


def _write_line(line: str) -> None:
    if _file_handle is None:
        return
    with _lock:
        _file_handle.write(line + '\n')
    if _mirror_console:
        try:
            from flo_ai.utils.logger import logger  # late import to avoid cycles

            logger.info('profile | %s', line)
        except Exception:
            pass


def record(name: str, duration_sec: float) -> None:
    """Record a duration against ``name`` without emitting flow lines.

    Useful when the surrounding code already computed an elapsed time (for
    example from an OpenTelemetry span) and you only want it counted in the
    summary.
    """
    if not _enabled:
        return
    _totals[name].append(duration_sec)


def _emit_enter(name: str, depth: int) -> None:
    indent = '  ' * depth
    ts = time.perf_counter() - _process_start
    _write_line(f'{ts:>10.3f}s {indent}-> {name}')


def _emit_exit(name: str, depth: int, elapsed: float, error: Optional[str]) -> None:
    indent = '  ' * depth
    ts = time.perf_counter() - _process_start
    status = f' [ERROR: {error}]' if error else ''
    _write_line(f'{ts:>10.3f}s {indent}<- {name} ({elapsed * 1000:.2f} ms){status}')


@asynccontextmanager
async def aprofile(name: str):
    """Async context manager that records a profiled section."""
    if not _enabled:
        yield
        return

    depth = _depth.get()
    _emit_enter(name, depth)
    token = _depth.set(depth + 1)
    start = time.perf_counter()
    err: Optional[str] = None
    try:
        yield
    except BaseException as e:  # noqa: BLE001 - we re-raise
        err = type(e).__name__
        raise
    finally:
        elapsed = time.perf_counter() - start
        _depth.reset(token)
        _totals[name].append(elapsed)
        _emit_exit(name, depth, elapsed, err)


@contextmanager
def profile(name: str):
    """Sync context manager that records a profiled section."""
    if not _enabled:
        yield
        return

    depth = _depth.get()
    _emit_enter(name, depth)
    token = _depth.set(depth + 1)
    start = time.perf_counter()
    err: Optional[str] = None
    try:
        yield
    except BaseException as e:  # noqa: BLE001 - we re-raise
        err = type(e).__name__
        raise
    finally:
        elapsed = time.perf_counter() - start
        _depth.reset(token)
        _totals[name].append(elapsed)
        _emit_exit(name, depth, elapsed, err)


def profile_async(name: Optional[str] = None) -> Callable:
    """Decorator for async functions."""

    def decorator(func: Callable) -> Callable:
        label = (
            name
            or f'{getattr(func, "__module__", "")}.{getattr(func, "__qualname__", getattr(func, "__name__", "<callable>"))}'
        )

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            async with aprofile(label):
                return await func(*args, **kwargs)

        return wrapper

    return decorator


def profile_sync(name: Optional[str] = None) -> Callable:
    """Decorator for synchronous functions."""

    def decorator(func: Callable) -> Callable:
        label = (
            name
            or f'{getattr(func, "__module__", "")}.{getattr(func, "__qualname__", getattr(func, "__name__", "<callable>"))}'
        )

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with profile(label):
                return func(*args, **kwargs)

        return wrapper

    return decorator


def write_summary() -> None:
    """Write a summary table of total time per section to the log file."""
    if not _enabled or _file_handle is None:
        return

    rows = []
    for name, durations in _totals.items():
        total = sum(durations)
        rows.append((total, len(durations), name))
    rows.sort(reverse=True)

    with _lock:
        _file_handle.write('\n=== SUMMARY (sections sorted by total wall time) ===\n')
        _file_handle.write(
            f"{'total_ms':>12}  {'count':>6}  {'avg_ms':>10}  {'max_ms':>10}  name\n"
        )
        for total, count, name in rows:
            durations = _totals[name]
            avg = total / count if count else 0.0
            mx = max(durations) if durations else 0.0
            _file_handle.write(
                f'{total * 1000:>12.2f}  {count:>6}  {avg * 1000:>10.2f}  '
                f'{mx * 1000:>10.2f}  {name}\n'
            )
        total_wall = time.perf_counter() - _process_start
        _file_handle.write(
            f'\nTotal wall time since profiler start: {total_wall * 1000:.2f} ms\n'
        )
        try:
            _file_handle.flush()
        except Exception:
            pass


_env_path = os.environ.get('FLO_AI_PROFILE')
if _env_path:
    try:
        enable_profiling(
            _env_path, mirror_console=_truthy(os.environ.get('FLO_AI_PROFILE_CONSOLE'))
        )
    except Exception:
        pass
