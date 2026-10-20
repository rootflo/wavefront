"""
LLM (Language Model) service factory

Supports multiple providers: OpenAI, Anthropic, Google, etc.
"""

from typing import Dict, Any
from call_processing.log.logger import logger

# Pipecat LLM services
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.openai.base_llm import BaseOpenAILLMService
from pipecat.services.google.llm import GoogleLLMService
from pipecat.services.groq.llm import GroqLLMService
from pipecat.services.azure.llm import AzureLLMService
# Add more as needed

# Reasoning-model knob (gpt-5 / o-series) that InputParams has no field for;
# sent through ``extra``. A low effort keeps voice-turn latency down.
OPENAI_EXTRA_PARAMS = ('reasoning_effort',)


def _openai_extra_params(parameters: Dict[str, Any]) -> Dict[str, Any]:
    return {k: parameters[k] for k in OPENAI_EXTRA_PARAMS if k in parameters}


# Reasoning models reject these with a 400. The LLM config UI pre-fills them
# (and refills them on every edit), so a config naming a reasoning effort is
# taken to be for a reasoning model and they are left out of the request.
REASONING_UNSUPPORTED_PARAMS = (
    'temperature',
    'top_p',
    'frequency_penalty',
    'presence_penalty',
)


def _without_reasoning_unsupported(parameters: Dict[str, Any]) -> Dict[str, Any]:
    if 'reasoning_effort' not in parameters:
        return parameters
    dropped = [k for k in REASONING_UNSUPPORTED_PARAMS if k in parameters]
    if dropped:
        logger.info(f'reasoning_effort set; not sending {dropped} to the LLM')
    return {
        k: v for k, v in parameters.items() if k not in REASONING_UNSUPPORTED_PARAMS
    }


class LLMServiceFactory:
    """Factory for creating LLM service instances from configuration"""

    @staticmethod
    def create_llm_service(llm_config: Dict[str, Any]):
        """
        Create LLM service from configuration

        Args:
            llm_config: {
                'type': 'openai' | 'anthropic' | 'gemini' | 'groq',
                'api_key': 'key',
                'llm_model': 'gpt-4',
                'parameters': {
                    'temperature': 0.7,
                    'max_tokens': 150,
                    ...
                }
            }

        Returns:
            Pipecat LLM service instance
        """
        llm_type = llm_config['type']
        api_key = llm_config['api_key']
        model = llm_config['llm_model']
        parameters = llm_config.get('parameters', {})

        if parameters is None:
            parameters = {}
        parameters = _without_reasoning_unsupported(parameters)

        logger.info(f'Creating LLM service: {llm_type} / {model}')

        if llm_type == 'openai':
            base_url = llm_config.get('base_url')
            if not base_url or base_url == 'https://api.openai.com/v1':
                return LLMServiceFactory._create_openai_llm(api_key, model, parameters)
            else:
                return LLMServiceFactory._create_openai_compatible_llm(
                    api_key, model, parameters, base_url
                )
        elif llm_type == 'azure_openai':
            base_url = llm_config.get('base_url')
            if not base_url:
                raise ValueError(
                    'Azure OpenAI requires base_url (endpoint) to be configured'
                )
            return LLMServiceFactory._create_azure_llm(
                api_key, model, parameters, base_url
            )
        elif llm_type == 'gemini':
            return LLMServiceFactory._create_google_llm(api_key, model, parameters)
        elif llm_type == 'groq':
            return LLMServiceFactory._create_groq_llm(api_key, model, parameters)
        else:
            raise ValueError(f'Unsupported LLM type: {llm_type}')

    @staticmethod
    def _create_openai_llm(api_key: str, model: str, parameters: Dict[str, Any]):
        """Create OpenAI LLM service"""
        # Build InputParams from the parameters dict
        params_dict = {}

        if 'temperature' in parameters:
            params_dict['temperature'] = parameters['temperature']
        if 'max_completion_tokens' in parameters:
            params_dict['max_completion_tokens'] = parameters['max_completion_tokens']
        if 'top_p' in parameters:
            params_dict['top_p'] = parameters['top_p']
        if 'frequency_penalty' in parameters:
            params_dict['frequency_penalty'] = parameters['frequency_penalty']
        if 'presence_penalty' in parameters:
            params_dict['presence_penalty'] = parameters['presence_penalty']
        if 'seed' in parameters:
            params_dict['seed'] = parameters['seed']
        extra = _openai_extra_params(parameters)
        if extra:
            params_dict['extra'] = extra
        if 'service_tier' in parameters:
            params_dict['service_tier'] = parameters['service_tier']

        # Create InputParams object
        input_params = BaseOpenAILLMService.InputParams(**params_dict)

        logger.info(
            f"OpenAI LLM config: model={model}, temp={params_dict.get('temperature', 'default')}"
        )

        return OpenAILLMService(api_key=api_key, model=model, params=input_params)

    @staticmethod
    def _create_openai_compatible_llm(
        api_key: str, model: str, parameters: Dict[str, Any], base_url: str
    ):
        """Create a BaseOpenAILLMService for OpenAI-compatible endpoints"""
        params_dict = {}

        if 'temperature' in parameters:
            params_dict['temperature'] = parameters['temperature']
        if 'max_completion_tokens' in parameters:
            params_dict['max_completion_tokens'] = parameters['max_completion_tokens']
        if 'top_p' in parameters:
            params_dict['top_p'] = parameters['top_p']
        if 'frequency_penalty' in parameters:
            params_dict['frequency_penalty'] = parameters['frequency_penalty']
        if 'presence_penalty' in parameters:
            params_dict['presence_penalty'] = parameters['presence_penalty']
        if 'seed' in parameters:
            params_dict['seed'] = parameters['seed']
        extra = _openai_extra_params(parameters)
        if extra:
            params_dict['extra'] = extra

        input_params = BaseOpenAILLMService.InputParams(**params_dict)

        logger.info(
            f"OpenAI-compatible LLM config: model={model}, base_url={base_url}, temp={params_dict.get('temperature', 'default')}"
        )

        return BaseOpenAILLMService(
            api_key=api_key, model=model, base_url=base_url, params=input_params
        )

    @staticmethod
    def _create_google_llm(api_key: str, model: str, parameters: Dict[str, Any]):
        """Create Google LLM service"""
        # Build InputParams from the parameters dict
        params_dict = {}

        if 'temperature' in parameters:
            params_dict['temperature'] = parameters['temperature']
        if 'max_tokens' in parameters:
            params_dict['max_tokens'] = parameters['max_tokens']
        if 'top_p' in parameters:
            params_dict['top_p'] = parameters['top_p']
        if 'top_k' in parameters:
            params_dict['top_k'] = parameters['top_k']

        # Create InputParams object
        input_params = GoogleLLMService.InputParams(**params_dict)

        logger.info(
            f"Google LLM config: model={model}, temp={params_dict.get('temperature', 'default')}"
        )

        return GoogleLLMService(api_key=api_key, model=model, params=input_params)

    @staticmethod
    def _create_groq_llm(api_key: str, model: str, parameters: Dict[str, Any]):
        """Create Groq LLM service"""
        # Build InputParams from the parameters dict
        params_dict = {}

        if 'temperature' in parameters:
            params_dict['temperature'] = parameters['temperature']
        if 'max_completion_tokens' in parameters:
            params_dict['max_completion_tokens'] = parameters['max_completion_tokens']
        if 'top_p' in parameters:
            params_dict['top_p'] = parameters['top_p']
        if 'frequency_penalty' in parameters:
            params_dict['frequency_penalty'] = parameters['frequency_penalty']
        if 'presence_penalty' in parameters:
            params_dict['presence_penalty'] = parameters['presence_penalty']
        if 'seed' in parameters:
            params_dict['seed'] = parameters['seed']
        extra = _openai_extra_params(parameters)
        if extra:
            params_dict['extra'] = extra

        logger.info(
            f"Groq LLM config: model={model}, temp={params_dict.get('temperature', 'default')}"
        )

        # GroqLLMService ignores ``params`` (it always hands its own settings to
        # the base class), so everything must go through ``settings``.
        return GroqLLMService(
            api_key=api_key,
            service_tier=parameters.get('service_tier'),
            settings=GroqLLMService.Settings(model=model, **params_dict),
        )

    @staticmethod
    def _create_azure_llm(
        api_key: str, model: str, parameters: Dict[str, Any], base_url: str = None
    ):
        """Create Azure OpenAI LLM service"""
        # Extract Azure specific params
        # api_version = parameters.get('api_version')

        # Build InputParams from the parameters dict
        params_dict = {}

        if 'temperature' in parameters:
            params_dict['temperature'] = parameters['temperature']
        if 'max_completion_tokens' in parameters:
            params_dict['max_completion_tokens'] = parameters['max_completion_tokens']
        if 'top_p' in parameters:
            params_dict['top_p'] = parameters['top_p']
        if 'frequency_penalty' in parameters:
            params_dict['frequency_penalty'] = parameters['frequency_penalty']
        if 'presence_penalty' in parameters:
            params_dict['presence_penalty'] = parameters['presence_penalty']
        if 'seed' in parameters:
            params_dict['seed'] = parameters['seed']
        extra = _openai_extra_params(parameters)
        if extra:
            params_dict['extra'] = extra

        logger.info(
            f"Azure OpenAI LLM config: model={model}, endpoint={base_url}, temp={params_dict.get('temperature', 'default')}, extra={extra or 'none'}"
        )

        # AzureLLMService ignores ``params`` (it always hands its own settings to
        # the base class), so everything must go through ``settings``.
        return AzureLLMService(
            api_key=api_key,
            endpoint=base_url,
            # api_version=api_version,
            settings=AzureLLMService.Settings(model=model, **params_dict),
        )
