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

        logger.info(f'Creating LLM service: {llm_type} / {model}')

        if llm_type == 'openai':
            return LLMServiceFactory._create_openai_llm(api_key, model, parameters)
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
        if 'service_tier' in parameters:
            params_dict['service_tier'] = parameters['service_tier']

        # Create InputParams object
        input_params = BaseOpenAILLMService.InputParams(**params_dict)

        logger.info(
            f"OpenAI LLM config: model={model}, temp={params_dict.get('temperature', 'default')}"
        )

        return OpenAILLMService(api_key=api_key, model=model, params=input_params)

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
        if 'service_tier' in parameters:
            params_dict['service_tier'] = parameters['service_tier']

        # Create InputParams object
        input_params = GroqLLMService.InputParams(**params_dict)

        logger.info(
            f"Groq LLM config: model={model}, temp={params_dict.get('temperature', 'default')}"
        )

        return GroqLLMService(api_key=api_key, model=model, params=input_params)

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

        # Create InputParams object
        input_params = BaseOpenAILLMService.InputParams(**params_dict)

        logger.info(
            f"Azure OpenAI LLM config: model={model}, endpoint={base_url}, temp={params_dict.get('temperature', 'default')}"
        )

        return AzureLLMService(
            api_key=api_key,
            endpoint=base_url,
            model=model,
            # api_version=api_version,
            params=input_params,
        )
