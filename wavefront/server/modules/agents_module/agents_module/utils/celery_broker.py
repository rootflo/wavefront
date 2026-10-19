"""Take a not-yet-delivered task back off the Celery broker queue."""

from celery import Celery

from agents_module.utils.celery_backpressure import broker_connection
from agents_module.utils.celery_settings import CeleryProducerSettings


class BrokerUnavailable(Exception):
    """The broker could not be asked, so nothing was removed."""


# LREMs the message whose headers.id is ARGV[1] from any of KEYS. Runs in Redis
# so the queue isn't shipped to the API, and atomically so no worker can take
# the task between the match and the LREM.
_REMOVE_BY_TASK_ID = """
local task_id = ARGV[1]
local page = 500
for _, key in ipairs(KEYS) do
  local len = redis.call('LLEN', key)
  for start = 0, len - 1, page do
    local chunk = redis.call('LRANGE', key, start, start + page - 1)
    for _, raw in ipairs(chunk) do
      if string.find(raw, task_id, 1, true) then
        local ok, msg = pcall(cjson.decode, raw)
        if ok and type(msg) == 'table' and type(msg.headers) == 'table'
            and msg.headers.id == task_id then
          return redis.call('LREM', key, 1, raw)
        end
      end
    end
  end
end
return 0
"""


def _queue_keys(channel, queue: str) -> list[str]:
    """One Redis list per priority step; all share the queue's hash tag."""
    keys = [channel._q_for_pri(queue, pri) for pri in channel.priority_steps]
    return list(dict.fromkeys(keys))


def remove_queued_task(
    app: Celery, task_id: str, settings: CeleryProducerSettings
) -> bool:
    """Remove the task from the queue `app` publishes to. Blocking.

    True means no worker received it. False means it wasn't on the queue:
    already picked up, or not enqueued yet. In-flight tasks are never touched.
    """
    try:
        with broker_connection(app, settings) as conn:
            channel = conn.default_channel
            keys = _queue_keys(channel, app.conf.task_default_queue)
            with channel.conn_or_acquire() as client:
                removed = client.eval(_REMOVE_BY_TASK_ID, len(keys), *keys, task_id)
    except Exception as exc:
        raise BrokerUnavailable(f'could not remove task {task_id}: {exc}') from exc
    return int(removed) > 0
