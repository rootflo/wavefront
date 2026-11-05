"""Start fetching read-only tools as soon as we know who is calling.

Started from the Twilio inbound webhook (before the call is answered) and
again when the media stream connects (every provider, while the greeting
plays). The second start finds the first one's result or running fetch in the
store, so a call never fetches twice.
"""

import asyncio
from typing import Any, Coroutine, Dict, List, Set
from uuid import UUID

from call_processing.log.logger import logger
from call_processing.services.common.context.store import CallContextStore
from call_processing.services.common.context.subject import CallSubject
from call_processing.services.common.tools.tool_wrapper_service import (
    ToolWrapperFactory,
)
from call_processing.services.common.voice_agent_cache_service import (
    VoiceAgentCacheService,
)

# Holds running prefetches so they aren't garbage-collected mid-flight
_background: Set[asyncio.Task] = set()


def run_in_background(coro: Coroutine[Any, Any, Any], name: str) -> None:
    async def guarded():
        try:
            await coro
        except Exception as e:
            logger.warning(f'Prefetch {name} failed: {e}')

    task = asyncio.create_task(guarded())
    _background.add(task)
    task.add_done_callback(_background.discard)


def start_prefetch(
    tools: List[Dict[str, Any]],
    subject: CallSubject,
    agent_id: str,
    store: CallContextStore,
) -> int:
    """Fire every prefetchable tool in the background. Never raises."""
    started = 0
    for tool in tools:
        if not (tool.get('association') or {}).get('is_enabled', True):
            continue
        try:
            job = ToolWrapperFactory.prefetch_job(tool, subject, agent_id, store)
        except Exception as e:
            logger.warning(f"Not prefetching tool '{tool.get('name')}': {e}")
            continue
        if job is not None:
            run_in_background(job(), name=f"tool '{tool.get('name')}'")
            started += 1
    if started:
        logger.info(f'Prefetching {started} tool(s) for call {subject.call_ref}')
    return started


async def prefetch_for_agent(
    voice_agent_cache_service: VoiceAgentCacheService,
    agent_id: str,
    subject: CallSubject,
    store: CallContextStore,
) -> None:
    """Load the agent's configs (warming them for the stream) and prefetch."""
    configs = await voice_agent_cache_service.get_all_agent_configs(UUID(agent_id))
    start_prefetch(configs.get('tools') or [], subject, agent_id, store)
