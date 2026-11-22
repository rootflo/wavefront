"""
LLM (Language Model) service factory

Supports OpenAI (and OpenAI-compatible endpoints), Azure OpenAI, Gemini, Groq
and AWS Bedrock.
"""

import dataclasses
import re
from typing import Any, Dict, Optional, Sequence

from pipecat.frames.frames import FunctionCallFromLLM
from pipecat.services.aws.llm import AWSBedrockLLMService
from pipecat.services.azure.llm import AzureLLMService
from pipecat.services.google.llm import GoogleLLMService
from pipecat.services.groq.llm import GroqLLMService
from pipecat.services.openai.base_llm import BaseOpenAILLMService
from pipecat.services.openai.llm import OpenAILLMService

from call_processing.log.logger import logger
from call_processing.services.common.providers.provider_types import LLMProvider
from call_processing.services.common.providers.provider_utils import pick

OPENAI_DEFAULT_BASE_URL = 'https://api.openai.com/v1'

# Stored parameters that map 1:1 onto the OpenAI-family Settings
OPENAI_SETTINGS_KEYS = (
    'temperature',
    'max_completion_tokens',
    'top_p',
    'frequency_penalty',
    'presence_penalty',
    'seed',
)

# Reasoning-model knob (gpt-5 / o-series) that Settings has no field for;
# sent through ``extra``. A low effort keeps voice-turn latency down.
OPENAI_EXTRA_PARAMS = ('reasoning_effort',)

GOOGLE_SETTINGS_KEYS = ('temperature', 'max_tokens', 'top_p', 'top_k')

# Gemini 3+ takes a thinking level, 2.5 a token budget (0 = off on Flash)
GOOGLE_THINKING_KEYS = ('thinking_level', 'thinking_budget')

# Bedrock Converse inferenceConfig, plus its performanceConfig latency mode
BEDROCK_SETTINGS_KEYS = ('temperature', 'max_tokens', 'top_p', 'latency')

# What Bedrock / OpenAI accept as a tool name: ^[a-zA-Z0-9_-]{1,64}$
_INVALID_TOOL_NAME_CHARS = re.compile(r'[^a-zA-Z0-9_-]')
_MAX_TOOL_NAME_LEN = 64

# Gemini also allows dots and colons, up to 128 characters
_GEMINI_INVALID_TOOL_NAME_CHARS = re.compile(r'[^a-zA-Z0-9_.:-]')
_GEMINI_MAX_TOOL_NAME_LEN = 128


def _openai_settings(parameters: Dict[str, Any]) -> Dict[str, Any]:
    settings = pick(parameters, OPENAI_SETTINGS_KEYS)
    extra = pick(parameters, OPENAI_EXTRA_PARAMS)
    if extra:
        settings['extra'] = extra
    return settings


class LLMServiceFactory:
    """Factory for creating LLM service instances from configuration"""

    @staticmethod
    def create_llm_service(llm_config: Dict[str, Any]):
        """Build a Pipecat LLM service from a stored LLM config.

        Reads ``type`` (an ``LLMProvider``), ``api_key``, ``llm_model``, an
        optional ``base_url`` (required for Azure) and provider ``parameters``.
        """
        llm = _create_llm_service(llm_config)
        _guard_tool_call_names(llm, llm_config['type'])
        return llm


def _create_llm_service(llm_config: Dict[str, Any]):
    llm_type = llm_config['type']
    api_key = llm_config['api_key']
    model = llm_config['llm_model']
    base_url = llm_config.get('base_url')
    parameters = llm_config.get('parameters') or {}

    logger.info(f'Creating LLM service: {llm_type} / {model}')

    if llm_type == LLMProvider.OPENAI:
        if base_url and base_url != OPENAI_DEFAULT_BASE_URL:
            return _create_openai_compatible_llm(api_key, model, parameters, base_url)
        return _create_openai_llm(api_key, model, parameters)
    if llm_type == LLMProvider.AZURE_OPENAI:
        if not base_url:
            raise ValueError(
                'Azure OpenAI requires base_url (endpoint) to be configured'
            )
        return _create_azure_llm(api_key, model, parameters, base_url)
    if llm_type == LLMProvider.GEMINI:
        return _create_google_llm(api_key, model, parameters)
    if llm_type == LLMProvider.GROQ:
        return _create_groq_llm(api_key, model, parameters)
    if llm_type == LLMProvider.BEDROCK:
        return _create_bedrock_llm(api_key, model, parameters)
    raise ValueError(f'Unsupported LLM type: {llm_type}')


def sanitize_tool_name(name: str, llm_type: Optional[str] = None) -> str:
    """A tool name the provider accepts, e.g. ``submit_identity游戏副本`` ->
    ``submit_identity``. Valid names are returned unchanged."""
    if llm_type == LLMProvider.GEMINI:
        invalid, max_len = _GEMINI_INVALID_TOOL_NAME_CHARS, _GEMINI_MAX_TOOL_NAME_LEN
    else:
        invalid, max_len = _INVALID_TOOL_NAME_CHARS, _MAX_TOOL_NAME_LEN
    cleaned = invalid.sub('', name or '')[:max_len]
    return cleaned or 'unknown_function'


def _guard_tool_call_names(llm: Any, llm_type: str) -> None:
    """Repair malformed tool names the model emits before they are dispatched.

    Models occasionally glue stray tokens onto a tool name. Pipecat answers an
    unknown name with "not available" and records the call in the context, and
    Bedrock / OpenAI then reject every later request whose history holds a name
    outside ``[a-zA-Z0-9_-]``: the conversation is stuck. Repairing the name
    here keeps the history valid and, when the repaired name is a registered
    tool (the usual case), runs the call the model meant.
    """
    run_function_calls = llm.run_function_calls

    async def run_guarded(function_calls: Sequence[FunctionCallFromLLM]):
        repaired = []
        for call in function_calls:
            name = sanitize_tool_name(call.function_name, llm_type)
            if name != call.function_name:
                logger.warning(
                    f'LLM emitted malformed tool name {call.function_name!r}, '
                    f'using {name!r}'
                )
                call = dataclasses.replace(call, function_name=name)
            repaired.append(call)
        await run_function_calls(repaired)

    llm.run_function_calls = run_guarded


def _log_settings(label: str, model: str, settings: Dict[str, Any], **extra) -> None:
    details = ''.join(f', {key}={value}' for key, value in extra.items())
    logger.info(
        f'{label} LLM config: model={model}, '
        f"temp={settings.get('temperature', 'default')}{details}"
    )


def _create_openai_llm(api_key: str, model: str, parameters: Dict[str, Any]):
    settings = _openai_settings(parameters)
    _log_settings('OpenAI', model, settings)
    return OpenAILLMService(
        api_key=api_key,
        # An init argument, not a Settings field
        service_tier=parameters.get('service_tier'),
        settings=OpenAILLMService.Settings(model=model, **settings),
    )


def _create_openai_compatible_llm(
    api_key: str, model: str, parameters: Dict[str, Any], base_url: str
):
    settings = _openai_settings(parameters)
    _log_settings('OpenAI-compatible', model, settings, base_url=base_url)
    return BaseOpenAILLMService(
        api_key=api_key,
        base_url=base_url,
        settings=BaseOpenAILLMService.Settings(model=model, **settings),
    )


def _create_azure_llm(
    api_key: str, model: str, parameters: Dict[str, Any], base_url: str
):
    settings = _openai_settings(parameters)
    _log_settings(
        'Azure OpenAI',
        model,
        settings,
        endpoint=base_url,
        extra=settings.get('extra', 'none'),
    )
    # AzureLLMService ignores ``params`` (it always hands its own settings to
    # the base class), so everything must go through ``settings``.
    return AzureLLMService(
        api_key=api_key,
        endpoint=base_url,
        settings=AzureLLMService.Settings(model=model, **settings),
    )


def _create_groq_llm(api_key: str, model: str, parameters: Dict[str, Any]):
    settings = _openai_settings(parameters)
    _log_settings('Groq', model, settings)
    # GroqLLMService ignores ``params`` too, so everything goes through ``settings``
    return GroqLLMService(
        api_key=api_key,
        service_tier=parameters.get('service_tier'),
        settings=GroqLLMService.Settings(model=model, **settings),
    )


def _create_google_llm(api_key: str, model: str, parameters: Dict[str, Any]):
    settings = pick(parameters, GOOGLE_SETTINGS_KEYS)
    thinking = {
        key: parameters[key]
        for key in GOOGLE_THINKING_KEYS
        if parameters.get(key) is not None
    }
    if thinking:
        settings['thinking'] = GoogleLLMService.ThinkingConfig(**thinking)
    _log_settings('Google', model, settings, thinking=thinking or 'default')
    return GoogleLLMService(
        api_key=api_key,
        settings=GoogleLLMService.Settings(model=model, **settings),
    )


def _create_bedrock_llm(
    secret_key: Optional[str], model: str, parameters: Dict[str, Any]
):
    region = parameters.get('aws_region')
    if not region:
        raise ValueError('AWS Bedrock requires aws_region to be configured')
    access_key = parameters.get('aws_access_key_id')
    # Both or neither: with neither, pipecat falls back to the ambient AWS
    # credential chain (env vars, instance/task role)
    if bool(access_key) != bool(secret_key):
        raise ValueError(
            'AWS Bedrock requires both aws_access_key_id and the secret access '
            'key, or neither to use the ambient AWS credentials'
        )
    settings = pick(parameters, BEDROCK_SETTINGS_KEYS)
    _log_settings(
        'AWS Bedrock',
        model,
        settings,
        region=region,
        credentials='explicit' if access_key else 'ambient',
    )
    return AWSBedrockLLMService(
        aws_access_key=access_key or None,
        aws_secret_key=secret_key or None,
        aws_region=region,
        settings=AWSBedrockLLMService.Settings(model=model, **settings),
    )
