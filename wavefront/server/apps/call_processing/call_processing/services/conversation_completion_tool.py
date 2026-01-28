"""
Conversation Completion Tool for Voice Agents

Provides LLM-callable conversation ending capabilities
"""

from typing import Dict, Any, Callable
from pipecat.services.llm_service import FunctionCallParams
from pipecat.frames.frames import TTSSpeakFrame, EndTaskFrame
from pipecat.processors.frame_processor import FrameDirection
from call_processing.log.logger import logger


class ConversationCompletionToolFactory:
    """Factory for creating conversation completion tool with runtime context"""

    @staticmethod
    def create_conversation_completion_tool(
        task_container: Dict[str, Any],
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
                farewell_message = arguments.get(
                    'farewell_message', 'Thank you for using our service! Goodbye!'
                )

                logger.info(
                    f'Conversation completion tool called - Farewell: "{farewell_message}"'
                )

                # Send farewell message via TTS
                await params.llm.push_frame(TTSSpeakFrame(farewell_message))

                # End the conversation
                await params.llm.push_frame(EndTaskFrame(), FrameDirection.UPSTREAM)

                logger.info('Conversation ended by LLM decision')

                # Return success result
                await params.result_callback(
                    {
                        'success': True,
                        'status': 'complete',
                        'farewell_sent': True,
                        'farewell_message': farewell_message,
                    }
                )

            except Exception as e:
                error_msg = f'Error ending conversation: {str(e)}'
                logger.error(error_msg, exc_info=True)
                await params.result_callback({'success': False, 'error': error_msg})

        return end_conversation
