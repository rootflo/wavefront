"""
Conversation Completion Tool for Voice Agents

Provides LLM-callable conversation ending capabilities
"""

from dataclasses import dataclass
from typing import Dict, Any, Callable, Mapping
from pipecat.services.llm_service import FunctionCallParams
from pipecat.frames.frames import EndFrame, TTSSpeakFrame
from pipecat.frames.frames import FunctionCallResultProperties
from call_processing.log.logger import logger
from call_processing.services.common.conversation_config import config_section

DEFAULT_FAREWELL = 'Thank you for using our service! Goodbye!'


@dataclass(frozen=True)
class EndConversationConfig:
    """Per agent, via ``conversation_config.end_conversation``::

        {"end_conversation": {"enabled": false, "farewell_message": "Goodbye!"}}

    Off by default: the bot never ends the call on its own. When on, the LLM may
    hang up after a clear goodbye, saying ``farewell_message`` unless it chose its own.
    """

    enabled: bool = False
    farewell_message: str = DEFAULT_FAREWELL

    @classmethod
    def from_agent_config(
        cls, agent_config: Mapping[str, Any]
    ) -> 'EndConversationConfig':
        raw = config_section(agent_config, 'end_conversation')
        farewell = raw.get('farewell_message')
        return cls(
            enabled=raw.get('enabled') is True,
            farewell_message=farewell.strip()
            if isinstance(farewell, str) and farewell.strip()
            else DEFAULT_FAREWELL,
        )


class ConversationCompletionToolFactory:
    """Factory for creating conversation completion tool with runtime context"""

    @staticmethod
    def create_conversation_completion_tool(
        task_container: Dict[str, Any],
        default_farewell: str = DEFAULT_FAREWELL,
    ) -> Callable:
        """
        Create conversation completion tool function with captured context

        Args:
            task_container: Dictionary containing PipelineTask (populated after task creation)
                           Format: {'task': PipelineTask | None}

        Returns:
            Async function compatible with Pipecat's function calling
        """

        async def end_conversation(params: FunctionCallParams):
            """
            LLM-callable function to end the conversation gracefully

            This function is called by the LLM when it determines the user
            wants to end the conversation. It sends a farewell message and
            terminates the pipeline.

            Parameters (from LLM):
                farewell_message: str - Optional custom farewell message
                                       (defaults to standard goodbye)
            """
            try:
                # Get task from container
                task = task_container.get('task')
                if not task:
                    error_msg = (
                        'Pipeline task not initialized in conversation completion tool'
                    )
                    logger.error(error_msg)
                    await params.result_callback({'success': False, 'error': error_msg})
                    return

                # Extract parameters
                arguments = params.arguments
                farewell_message = arguments.get('farewell_message') or default_farewell

                logger.info(
                    f'Conversation completion tool called - Farewell: "{farewell_message}"'
                )

                # Stop further LLM turns; speak farewell then end cleanly in order
                # so we do not cut mid-audio (which sounds like a sharp click).
                await params.result_callback(
                    {
                        'success': True,
                        'status': 'complete',
                        'farewell_sent': True,
                        'farewell_message': farewell_message,
                    },
                    properties=FunctionCallResultProperties(run_llm=False),
                )
                await task.queue_frame(TTSSpeakFrame(farewell_message))
                await task.queue_frame(EndFrame())

                logger.info('Conversation end queued (farewell + EndFrame)')

            except Exception as e:
                error_msg = f'Error ending conversation: {str(e)}'
                logger.error(error_msg, exc_info=True)
                await params.result_callback({'success': False, 'error': error_msg})

        return end_conversation
