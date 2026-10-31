"""The `llm_inference_config_id` override hands the agent (and the Celery
payload) the plaintext api_key, even when it is stored encrypted."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from common_module.response_formatter import ResponseFormatter
from common_module.security.secret_cipher import SecretCipher
from db_repo_module.models.llm_inference_config import LlmInferenceConfig
from flo_cloud._types import FloCipher
from flo_cloud.envelope import ENVELOPE_PREFIX, EnvelopeCipher
from llm_inference_config_module.services.llm_inference_config_service import (
    LlmInferenceConfigService,
)

from agents_module.controllers import agent_controller
from agents_module.controllers import async_inference_controller
from agents_module.models.agent_schemas import AgentInferenceRequest

API_KEY = 'sk-live-123'


class FakeKms(FloCipher):
    def encrypt(self, plaintext):
        data = plaintext.encode() if isinstance(plaintext, str) else plaintext
        return b'kms:' + bytes(reversed(data))

    def decrypt(self, ciphertext):
        return bytes(reversed(ciphertext[4:]))

    def encrypt_for_storage(self, plaintext):
        raise NotImplementedError

    def decrypt_from_storage(self, stored):
        raise NotImplementedError


@pytest.fixture(params=[True, False], ids=['flag_on', 'flag_off'])
def config_service(request):
    if request.param:
        cipher = SecretCipher(
            enabled=True, envelope_factory=lambda: EnvelopeCipher(FakeKms())
        )
    else:
        cipher = SecretCipher(enabled=False)

    row = LlmInferenceConfig(
        id=uuid.uuid4(),
        llm_model='gpt-4o',
        display_name='GPT-4o',
        type='openai',
        api_key=cipher.protect(API_KEY),
        is_deleted=False,
    )
    assert row.api_key.startswith(ENVELOPE_PREFIX) is request.param

    repository = MagicMock()
    repository.find_one = AsyncMock(return_value=row)
    cache = MagicMock()
    cache.get_str = MagicMock(return_value=None)
    return LlmInferenceConfigService(repository, cache, MagicMock(), cipher), row.id


@pytest.fixture
def request_obj():
    req = MagicMock()
    req.headers = {}
    req.state.session = None
    return req


async def test_async_override_enqueues_the_plaintext_config(
    request_obj, config_service
):
    service, config_id = config_service
    execution = MagicMock()
    execution.queue_is_saturated = AsyncMock(return_value=False)
    execution.create_and_enqueue_agent = AsyncMock(
        return_value=MagicMock(execution_id='e1', model_dump=lambda **_: {})
    )
    crud = MagicMock()
    crud.get_agent = AsyncMock(return_value={'version': 1, 'name': 'a'})

    await async_inference_controller.async_agent_inference(
        request=request_obj,
        agent_id=uuid.uuid4(),
        payload=AgentInferenceRequest(
            inputs='hello', llm_inference_config_id=config_id
        ),
        version=None,
        async_agentic_execution_service=execution,
        agent_crud_service=crud,
        llm_inference_config_service=service,
        response_formatter=ResponseFormatter(),
    )

    llm_config = execution.create_and_enqueue_agent.await_args.kwargs['llm_config']
    assert llm_config['api_key'] == API_KEY
    # The worker rebuilds it with LlmInferenceConfig(**llm_config).
    assert LlmInferenceConfig(**llm_config).api_key == API_KEY


async def test_sync_override_builds_the_agent_with_the_plaintext_key(
    request_obj, config_service
):
    service, config_id = config_service
    inference = MagicMock()
    inference.perform_inference = AsyncMock(
        return_value=([SimpleNamespace(content='ok')], 0.1)
    )

    await agent_controller.agent_inference(
        request=request_obj,
        namespace='default',
        agent_id='a',
        agent_inference_payload=AgentInferenceRequest(
            inputs='hello', llm_inference_config_id=config_id
        ),
        version=None,
        agent_inference_service=inference,
        response_formatter=ResponseFormatter(),
        llm_inference_config_service=service,
    )

    llm_config = inference.perform_inference.await_args.kwargs['llm_config']
    assert llm_config.api_key == API_KEY
