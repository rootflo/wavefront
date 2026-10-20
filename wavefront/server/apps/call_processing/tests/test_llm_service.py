import pytest

from call_processing.services.llm_service import LLMServiceFactory

PARAMS = {
    'temperature': 0.2,
    'max_completion_tokens': 150,
}


def _create(llm_type, parameters, **config):
    return LLMServiceFactory.create_llm_service(
        {
            'type': llm_type,
            'api_key': 'test-key',
            'llm_model': 'test-model',
            'parameters': parameters,
            **config,
        }
    )


@pytest.mark.parametrize(
    'llm_type, config',
    [
        ('azure_openai', {'base_url': 'https://test.openai.azure.com'}),
        ('openai', {}),
        ('openai', {'base_url': 'https://compatible.example.com/v1'}),
        ('groq', {}),
    ],
)
def test_parameters_reach_the_request_settings(llm_type, config):
    # Azure and Groq ignore ``params``, which silently dropped all of these before
    settings = _create(llm_type, PARAMS, **config)._settings

    assert settings.model == 'test-model'
    assert settings.temperature == 0.2
    assert settings.max_completion_tokens == 150
    assert settings.extra == {}


def test_reasoning_effort_is_sent_in_the_request():
    llm = _create(
        'azure_openai',
        {'reasoning_effort': 'none', 'max_completion_tokens': 500},
        base_url='https://test.openai.azure.com',
    )

    request = llm.build_chat_completion_params({'messages': []})

    assert request['reasoning_effort'] == 'none'
    assert request['max_completion_tokens'] == 500


def test_sampling_params_go_out_alongside_reasoning_effort():
    # GPT-OSS and GPT-6 Astra take both; the UI only saves what the model accepts
    llm = _create('groq', {'reasoning_effort': 'low', 'temperature': 0.7, 'top_p': 0.9})

    request = llm.build_chat_completion_params({'messages': []})

    assert request['reasoning_effort'] == 'low'
    assert request['temperature'] == 0.7
    assert request['top_p'] == 0.9


@pytest.mark.parametrize(
    'parameters, expected',
    [
        ({'thinking_level': 'minimal'}, {'thinking_level': 'minimal'}),
        ({'thinking_budget': 0}, {'thinking_budget': 0}),
    ],
)
def test_gemini_thinking_reaches_the_settings(parameters, expected):
    settings = _create('gemini', {'temperature': 1.0, **parameters})._settings

    assert settings.temperature == 1.0
    thinking = settings.thinking.model_dump(exclude_none=True)
    assert thinking == expected


def test_gemini_without_thinking_leaves_the_model_default():
    settings = _create('gemini', {'temperature': 0.5})._settings

    assert settings.thinking is None


def test_unsupported_keys_are_not_forwarded():
    # gpt-4.1 400s on verbosity; configs saved before it was removed may hold it
    llm = _create(
        'azure_openai', {'verbosity': 'low'}, base_url='https://test.openai.azure.com'
    )

    request = llm.build_chat_completion_params({'messages': []})

    assert 'verbosity' not in request


def test_no_extra_params_when_none_configured():
    llm = _create('azure_openai', {}, base_url='https://test.openai.azure.com')

    request = llm.build_chat_completion_params({'messages': []})

    assert 'reasoning_effort' not in request
    assert llm._settings.extra == {}
