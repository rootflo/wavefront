"""
Language Detection Tool for Multi-Language Voice Agents

Provides LLM-callable language detection and switching capabilities
"""

from typing import Dict, Any, List, Callable
from pipecat.services.llm_service import FunctionCallParams
from pipecat.frames.frames import LLMMessagesUpdateFrame
from call_processing.log.logger import logger
from call_processing.constants.language_config import LANGUAGE_INSTRUCTIONS


class LanguageDetectionToolFactory:
    """Factory for creating language detection tool with runtime context"""

    @staticmethod
    def create_language_detection_tool(
        task_container: Dict[str, Any],
        language_switcher: Any,
        stt_language_switcher: Any,
        context_container: Dict[str, Any],
        supported_languages: List[str],
        default_language: str,
        language_state: Dict[str, Any],
    ) -> Callable:
        """
        Create language detection tool function with captured context

        Args:
            task_container: Dictionary containing PipelineTask (populated after task creation)
                           Format: {'task': PipelineTask | None}
            language_switcher: LanguageSwitcher instance that manages TTS routing
            stt_language_switcher: STTLanguageSwitcher instance that manages STT routing
            context_container: Dictionary containing LLMContext (populated after context creation)
                              Format: {'context': LLMContext | None}
            supported_languages: List of supported language codes
            default_language: Default language code
            language_state: Dictionary to track current language and switch count
                           Format: {'current_language': str, 'switch_count': int, 'original_system_prompt': str}

        Returns:
            Async function compatible with Pipecat's function calling
        """

        async def detect_and_switch_language(params: FunctionCallParams):
            """
            LLM-callable function to detect and switch conversation language

            This function is called by the LLM when it determines the user
            wants to switch to a different language. It validates the request,
            performs the service switch, and updates the system prompt.

            Parameters (from LLM):
                target_language: str - Language code to switch to (e.g., 'es', 'hi', 'en')
                user_intent: str - User's stated language preference (for logging)
            """
            try:
                # Get task and context from containers
                task = task_container.get('task')
                if not task:
                    error_msg = (
                        'Pipeline task not initialized in language detection tool'
                    )
                    logger.error(error_msg)
                    await params.result_callback({'success': False, 'error': error_msg})
                    return

                context = context_container.get('context')
                if not context:
                    error_msg = 'LLM context not initialized in language detection tool'
                    logger.error(error_msg)
                    await params.result_callback({'success': False, 'error': error_msg})
                    return

                # Extract parameters
                arguments = params.arguments
                target_language = arguments.get('target_language', '').lower()
                user_intent = arguments.get('user_intent', 'Unknown')

                current_language = language_state.get(
                    'current_language', default_language
                )
                switch_count = language_state.get('switch_count', 0)

                logger.info(
                    f'Language detection tool called - Target: {target_language}, '
                    f'Current: {current_language}, User intent: {user_intent}'
                )

                # Validation 1: Check if target language is supported
                if target_language not in supported_languages:
                    logger.warning(
                        f"Language switch attempted for unsupported language: '{target_language}'"
                    )
                    await params.result_callback(
                        {
                            'success': False,
                            'error': (
                                f"'{target_language}' is not a supported language. "
                                f"Tell the user you're sorry but this language is not supported, "
                                f"and that you can only converse in: {', '.join(supported_languages)}. "
                                f"Do not attempt any language switch."
                            ),
                            'current_language': current_language,
                            'supported_languages': supported_languages,
                        }
                    )
                    return

                # Validation 2: Check if already in target language
                if target_language == current_language:
                    logger.info(f'Already using language: {target_language}')
                    await params.result_callback(
                        {
                            'success': True,
                            'message': f'Already using {target_language}',
                            'current_language': current_language,
                            'switch_performed': False,
                        }
                    )
                    return

                # Perform language switch
                try:
                    # Update TTS language switcher state
                    language_switcher.set_language(target_language)

                    # Update STT language switcher state
                    stt_language_switcher.set_language(target_language)

                    logger.info(
                        f'Switched TTS and STT language from {current_language} to {target_language}'
                    )

                    # Update system prompt with language instruction
                    language_instruction = LANGUAGE_INSTRUCTIONS.get(
                        target_language,
                        LANGUAGE_INSTRUCTIONS.get('en', 'Respond in English.'),
                    )

                    # Get base prompt without language instruction (must exist for multi-language)
                    base_prompt = language_state.get('original_system_prompt')
                    if not base_prompt:
                        error_msg = 'Original system prompt not found in language state'
                        logger.error(error_msg)
                        await params.result_callback(
                            {'success': False, 'error': error_msg}
                        )
                        return

                    # Append new language instruction to clean base prompt
                    updated_content = f'{base_prompt}\n\n{language_instruction}'
                    updated_system_message = {
                        'role': 'system',
                        'content': updated_content,
                    }

                    # Update context
                    current_messages = context.get_messages()
                    new_messages = [updated_system_message] + current_messages[1:]
                    await task.queue_frame(
                        LLMMessagesUpdateFrame(new_messages, run_llm=False)
                    )

                    logger.info(
                        f'Updated system prompt with {target_language} instruction'
                    )

                    # Update state
                    language_state['current_language'] = target_language
                    language_state['switch_count'] = switch_count + 1

                    # Return success result
                    await params.result_callback(
                        {
                            'success': True,
                            'message': f'Language switched to {target_language}',
                            'previous_language': current_language,
                            'current_language': target_language,
                            'switch_performed': True,
                            'switch_count': language_state['switch_count'],
                        }
                    )

                except Exception as e:
                    error_msg = f'Error switching services: {str(e)}'
                    logger.error(error_msg, exc_info=True)
                    await params.result_callback(
                        {
                            'success': False,
                            'error': error_msg,
                            'current_language': current_language,
                        }
                    )

            except Exception as e:
                error_msg = f'Error in language detection tool: {str(e)}'
                logger.error(error_msg, exc_info=True)
                await params.result_callback({'success': False, 'error': error_msg})

        return detect_and_switch_language
