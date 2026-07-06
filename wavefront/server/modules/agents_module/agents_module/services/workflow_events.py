import asyncio
from typing import Dict, Callable, List
from flo_ai.arium import AriumEventType, AriumEvent
from common_module.log.logger import logger
from agents_module.models.workflow_schemas import WorkflowEventMessage


class WorkflowEventStreamer:
    """Manager for HTTP streaming workflow events, isolated per execution."""

    def __init__(self):
        self.event_queues: Dict[str, asyncio.Queue] = {}

    def create_queue(self, execution_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self.event_queues[execution_id] = queue
        logger.info(f'Created event queue for execution {execution_id}')
        return queue

    async def add_event(self, execution_id: str, event_message: WorkflowEventMessage):
        queue = self.event_queues.get(execution_id)
        if queue is None:
            return
        try:
            await queue.put(event_message.model_dump())
        except Exception as e:
            logger.error(f'Error queuing event for execution {execution_id}: {e}')

    def cleanup_queue(self, execution_id: str):
        if execution_id in self.event_queues:
            del self.event_queues[execution_id]
            logger.info(f'Cleaned up event queue for execution {execution_id}')


# Global event streamer instance
event_streamer = WorkflowEventStreamer()


DEFAULT_EVENTS_FILTER: List[AriumEventType] = [
    AriumEventType.WORKFLOW_STARTED,
    AriumEventType.WORKFLOW_COMPLETED,
    AriumEventType.WORKFLOW_FAILED,
    AriumEventType.NODE_STARTED,
    AriumEventType.NODE_COMPLETED,
    AriumEventType.NODE_FAILED,
    AriumEventType.ROUTER_DECISION,
    AriumEventType.EDGE_TRAVERSED,
]


def create_workflow_event_callback(
    execution_id: str,
    namespace: str,
    workflow_id: str,
) -> Callable[[AriumEvent], None]:
    """
    Create an event callback scoped to a single execution_id so concurrent
    runs of the same workflow never share a queue.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    def event_callback(event: AriumEvent) -> None:
        try:
            event_message = WorkflowEventMessage(
                event_type=event.event_type.value,
                timestamp=event.timestamp,
                workflow_id=workflow_id,
                namespace=namespace,
                node_name=event.node_name,
                node_type=event.node_type,
                execution_time=event.execution_time,
                error=event.error,
                router_choice=event.router_choice,
                node_output=event.node_output,
                metadata=event.metadata,
            )
            running_loop = loop
            try:
                running_loop = asyncio.get_running_loop()
            except RuntimeError:
                pass

            if running_loop is not None:
                asyncio.ensure_future(
                    event_streamer.add_event(execution_id, event_message),
                    loop=running_loop,
                )
            else:
                logger.warning(
                    f'No event loop available to queue event {event.event_type.value} '
                    f'for execution {execution_id}'
                )
        except Exception as e:
            logger.error(
                f'Error in workflow event callback for execution {execution_id}: {e}'
            )

    return event_callback
