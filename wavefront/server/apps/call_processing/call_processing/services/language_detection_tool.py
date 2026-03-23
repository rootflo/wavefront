"""
Language Detection Tool for Multi-Language Voice Agents

Provides LLM-callable language detection and switching capabilities
"""

from typing import Dict, Any, List, Callable
from pipecat.services.llm_service import FunctionCallParams
from call_processing.log.logger import logger
from call_processing.constants.language_config import LANGUAGE_INSTRUCTIONS
from call_processing.services.tts_service import TTSServiceFactory
from call_processing.services.stt_service import STTServiceFactory


class LanguageDetectionToolFactory:
    """Factory for creating language detection tool with runtime context"""

    @staticmethod
    def create_language_detection_tool(
        task_container: Dict[str, Any],
        tts_provider: str,
        stt_provider: str,
        tts_voice_ids: Dict[str, str],
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
            tts_provider: TTS provider name (e.g. 'elevenlabs', 'azure')
            stt_provider: STT provider name (e.g. 'deepgram', 'azure')
            tts_voice_ids: Dict mapping language code -> voice ID for TTS
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
                    # Queue TTS settings update (voice + language)
                    tts_frame = TTSServiceFactory.create_language_update_frame(
                        tts_provider,
                        target_language,
                        tts_voice_ids.get(target_language),
                    )
                    tts_frame_queued = False
                    if tts_frame:
                        await task.queue_frame(tts_frame)
                        tts_frame_queued = True

                    # Queue STT settings update (language)
                    stt_frame = STTServiceFactory.create_language_update_frame(
                        stt_provider, target_language
                    )
                    stt_frame_queued = False
                    if stt_frame:
                        await task.queue_frame(stt_frame)
                        stt_frame_queued = True

                    log_msg = (
                        f'Language update {current_language} -> {target_language}: '
                        f'TTS={"queued" if tts_frame_queued else "skipped"}, '
                        f'STT={"queued" if stt_frame_queued else "skipped"}'
                    )
                    if tts_frame_queued or stt_frame_queued:
                        logger.info(log_msg)
                    else:
                        logger.error(log_msg)

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
                    updated_content = f'{language_instruction}\n\n{base_prompt}'

                    # Mutate the system message in-place on the context object so
                    # the full conversation history (including the current tool
                    # call + result being appended by pipecat) is preserved.
                    # Using LLMMessagesUpdateFrame would snapshot messages BEFORE
                    # pipecat appends the tool result, stripping it from context
                    # and causing a second spurious tool call on LLM continuation.
                    current_messages = context.get_messages()
                    current_messages[0] = {'role': 'system', 'content': updated_content}
                    context.set_messages(current_messages)

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
