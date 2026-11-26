# Concurrency rules

Each floware and floconsole worker runs one asyncio event loop. A blocking call
inside `async def` stalls every request on that worker, not just its own. These
rules keep the loop free. `modules/common_module/tests/test_event_loop_guard.py`
enforces them in CI.

## Rules

1. **Blocking calls go through `run_in_pool`.** Inside `async def`, never call
   sync I/O or CPU-heavy code directly: `time.sleep`, `requests`, the sync
   Redis client or sync `CacheManager` methods, `open()`, KMS, cloud storage,
   bcrypt. Prefer an async client where one exists: `await cache_manager.aget_str(...)`,
   or `try_a*` when a Redis failure should not fail the request. Otherwise use
   a named, bounded pool:

   ```python
   from common_module.blocking_io import Pool, run_in_pool

   data = await run_in_pool(Pool.STORAGE, storage.read_file, bucket, key)
   ```

   The lanes are `Pool.KMS`, `Pool.STORAGE` and `Pool.CPU`. A full pool raises
   `BlockingPoolBusyError`, which the app turns into a 503 with `Retry-After`.
   Never swallow it in a broad `except Exception`: re-raise it. Do not use
   `asyncio.to_thread` or `loop.run_in_executor`. They share one unbounded
   default executor that queues forever under load.

2. **No background task or thread without an owner.** `asyncio.create_task`,
   `ensure_future`, `threading.Thread` and `ThreadPoolExecutor` need an owner
   that holds a reference, stops the work on shutdown and awaits it. For
   request-scoped fan-out, use `asyncio.TaskGroup` (owned by its `async with`).
   A bare `create_task` whose result is dropped can be garbage-collected
   mid-run, and its exception is never seen.

3. **Streaming generators cancel their work in `try/finally`.** When a client
   disconnects, Starlette closes the generator with `GeneratorExit` or
   `CancelledError`. Any task the generator started must be cancelled in
   `finally`, or it keeps running for nobody:

   ```python
   task = asyncio.create_task(run_inference(...))  # concurrency: allowed
   try:
       async for chunk in stream(queue):
           yield chunk
   finally:
       if not task.done():
           task.cancel()
   ```

4. **Never `await task.cancel()`.** `Task.cancel()` returns a `bool`, so
   awaiting it raises `TypeError`. Call `task.cancel()`, then
   `await asyncio.gather(task, return_exceptions=True)` if you need it gone.

Coming later: a shared supervisor for background tasks (`spawn`,
`run_service` and supervised threads). Once it lands, rule 2 will point at it.
Until then, keep ownership local and explicit.

## When the guard fails

The guard walks the server code (excluding tests, alembic, background_jobs and
scripts) and reports `path:line function rule`. Fix the call. If the pattern is
genuinely right (for example, the code that owns a pool or the lag monitor's
watchdog thread), add `# concurrency: allowed` on that line with a short reason.

`modules/common_module/tests/event_loop_guard_allowlist.txt` lists code that
predates the guard, by `path::function::rule`. The list only shrinks. Delete an
entry when you fix it; the guard fails on entries that no longer match. Do not
add new entries.

Run it:

```bash
pytest -q modules/common_module/tests/test_event_loop_guard.py
```
