import asyncio
from typing import Dict, Callable, List
from flo_ai.arium import AriumEventType, AriumEvent
from common_module.log.logger import logger
from agents_module.models.workflow_schemas import WorkflowEventMessage


class WorkflowEventStreamer:
    """Manager for HTTP streaming workflow events with user isolation using asyncio.Queue"""

    def __init__(self):
        # Store event queues by user-specific workflow key (user_id_namespace_workflow_id)
        self.event_queues: Dict[str, asyncio.Queue] = {}

    def get_workflow_key(self, user_id: str, namespace: str, workflow_id: str) -> str:
        """Generate unique key for user-specific workflow"""
        return f'{user_id}_{namespace}_{workflow_id}'

    def get_or_create_queue(
        self, user_id: str, namespace: str, workflow_id: str
    ) -> asyncio.Queue:
        """Get or create event queue for user-specific workflow"""
        workflow_key = self.get_workflow_key(user_id, namespace, workflow_id)

        if workflow_key not in self.event_queues:
            self.event_queues[workflow_key] = asyncio.Queue()
            logger.info(
                f'Created event queue for user {user_id}, workflow {namespace}/{workflow_id}'
            )

        return self.event_queues[workflow_key]

    async def add_event(
        self,
        user_id: str,
        namespace: str,
        workflow_id: str,
        event_message: WorkflowEventMessage,
    ):
        """Add event to the queue for user-specific workflow"""
        workflow_key = self.get_workflow_key(user_id, namespace, workflow_id)

        if workflow_key not in self.event_queues:
            # Create queue if it doesn't exist (workflow started before streaming)
            self.event_queues[workflow_key] = asyncio.Queue()
            logger.info(
                f'Created event queue for user {user_id}, workflow {namespace}/{workflow_id}'
            )

        try:
            # Convert event message to dict for JSON serialization
            event_dict = event_message.model_dump()
            await self.event_queues[workflow_key].put(event_dict)
            logger.debug(
                f"Event queued for user {user_id}, workflow {namespace}/{workflow_id}: {event_dict['event_type']}"
            )
        except Exception as e:
            logger.error(
                f'Error queuing event for user {user_id}, workflow {namespace}/{workflow_id}: {e}'
            )

    def cleanup_queue(self, user_id: str, namespace: str, workflow_id: str):
        """Remove event queue for user-specific workflow"""
        workflow_key = self.get_workflow_key(user_id, namespace, workflow_id)

        if workflow_key in self.event_queues:
            del self.event_queues[workflow_key]
            logger.info(
                f'Cleaned up event queue for user {user_id}, workflow {namespace}/{workflow_id}'
            )


# Global event streamer instance
event_streamer = WorkflowEventStreamer()


# Hardcoded events filter - listen to all event types
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
    user_id: str, namespace: str, workflow_id: str
) -> Callable[[AriumEvent], None]:
    """
    Create a hardcoded event callback function for user-specific HTTP streaming

    Args:
        user_id: User ID from authenticated session
        namespace: Workflow namespace
        workflow_id: Workflow ID

    Returns:
        Event callback function that queues events for HTTP streaming
    """

    def event_callback(event: AriumEvent) -> None:
        """
        Hardcoded callback that converts AriumEvent to WorkflowEventMessage and queues for HTTP streaming
        """
        try:
            # Convert AriumEvent to WorkflowEventMessage
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
                metadata=event.metadata,
            )

            # Queue event for HTTP streaming (async operation, we'll queue it)
            asyncio.create_task(
                event_streamer.add_event(user_id, namespace, workflow_id, event_message)
            )

            logger.debug(
                f'Workflow event queued: {event.event_type.value} for user {user_id}, workflow {namespace}/{workflow_id}'
            )

        except Exception as e:
            logger.error(f'Error in workflow event callback for user {user_id}: {e}')

    return event_callback
