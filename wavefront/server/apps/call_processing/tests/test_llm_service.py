import pytest
from pipecat.frames.frames import FunctionCallFromLLM
from pipecat.services.openai.llm import OpenAILLMService

from call_processing.services.common.providers.llm_service import (
    LLMServiceFactory,
    sanitize_tool_name,
)

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


def _bedrock(parameters, api_key='test-secret'):
    return LLMServiceFactory.create_llm_service(
        {
            'type': 'bedrock',
            'api_key': api_key,
            'llm_model': 'global.anthropic.claude-haiku-5-5',
            'parameters': parameters,
        }
    )


def test_bedrock_settings_and_credentials():
    llm = _bedrock(
        {
            'aws_access_key_id': 'AKIATEST',
            'aws_region': 'us-east-1',
            'temperature': 0.3,
            'max_tokens': 300,
            'latency': 'optimized',
        }
    )

    assert llm._settings.model == 'global.anthropic.claude-haiku-5-5'
    assert llm._settings.latency == 'optimized'
    assert llm._build_inference_config() == {'maxTokens': 300, 'temperature': 0.3}
    assert llm._aws_params['aws_access_key_id'] == 'AKIATEST'
    assert llm._aws_params['aws_secret_access_key'] == 'test-secret'
    assert llm._aws_params['region_name'] == 'us-east-1'


def test_bedrock_unset_sampling_is_not_sent():
    # Claude 5.x on Bedrock rejects temperature / top_p
    llm = _bedrock({'aws_access_key_id': 'AKIATEST', 'aws_region': 'us-east-1'})

    assert llm._build_inference_config() == {}


def test_bedrock_requires_region():
    with pytest.raises(ValueError, match='aws_region'):
        _bedrock({'aws_access_key_id': 'AKIATEST'})


def test_bedrock_rejects_half_a_key_pair():
    with pytest.raises(ValueError, match='aws_access_key_id'):
        _bedrock({'aws_region': 'us-east-1'})


@pytest.mark.parametrize(
    'name, expected',
    [
        ('submit_identity', 'submit_identity'),
        ('submit_identity游戏副本', 'submit_identity'),
        ('get weather!', 'getweather'),
        ('x' * 80, 'x' * 64),
        ('游戏', 'unknown_function'),
    ],
)
def test_sanitize_tool_name(name, expected):
    assert sanitize_tool_name(name) == expected


async def test_malformed_tool_names_are_repaired_before_dispatch(monkeypatch):
    dispatched = []

    async def fake_run(self, function_calls):
        dispatched.extend(function_calls)

    monkeypatch.setattr(OpenAILLMService, 'run_function_calls', fake_run)
    llm = _create('openai', {})

    await llm.run_function_calls(
        [
            FunctionCallFromLLM(
                function_name='submit_identity游戏副本',
                tool_call_id='1',
                arguments={'field': 'name'},
                context=None,
            ),
            FunctionCallFromLLM(
                function_name='end_conversation',
                tool_call_id='2',
                arguments={},
                context=None,
            ),
        ]
    )

    assert [c.function_name for c in dispatched] == [
        'submit_identity',
        'end_conversation',
    ]
    assert dispatched[0].arguments == {'field': 'name'}
    assert dispatched[0].tool_call_id == '1'
