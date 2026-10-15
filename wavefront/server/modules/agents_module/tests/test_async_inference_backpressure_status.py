"""A saturated queue answers 429, not 422 or 500, at both check points."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from common_module.response_formatter import ResponseFormatter

from agents_module.controllers import async_inference_controller as controller
from agents_module.models.agent_schemas import AgentInferenceRequest
from agents_module.models.workflow_schemas import WorkflowInferenceRequest
from agents_module.utils.celery_backpressure import QueueBackpressure


@pytest.fixture
def formatter():
    return ResponseFormatter()


@pytest.fixture
def request_obj():
    req = MagicMock()
    req.headers = {}
    req.state.session = None
    return req


@pytest.fixture
def saturated_service():
    """A service whose enqueue refuses, as it does past the controller check."""
    service = MagicMock()
    # Passes the controller's pre-check; the service then raises.
    service.queue_is_saturated = AsyncMock(return_value=False)
    service.create_and_enqueue_agent = AsyncMock(
        side_effect=QueueBackpressure(10000, 10000, 45)
    )
    service.create_and_enqueue_workflow = AsyncMock(
        side_effect=QueueBackpressure(10000, 10000, 45)
    )
    return service


@pytest.fixture
def agent_crud():
    crud = MagicMock()
    crud.get_agent = AsyncMock(return_value={'version': 1, 'name': 'a'})
    return crud


@pytest.fixture
def workflow_crud():
    crud = MagicMock()
    crud.get_workflow = AsyncMock(
        return_value={'name': 'wf', 'namespace': 'default', 'version': 1}
    )
    return crud


async def test_agent_route_answers_429_when_the_service_refuses(
    request_obj, saturated_service, agent_crud, formatter
):
    response = await controller.async_agent_inference(
        request=request_obj,
        agent_id=uuid.uuid4(),
        payload=AgentInferenceRequest(inputs='hello'),
        version=None,
        async_agentic_execution_service=saturated_service,
        agent_crud_service=agent_crud,
        llm_inference_config_service=MagicMock(),
        response_formatter=formatter,
    )

    assert response.status_code == 429
    assert response.headers['retry-after'] == '45'


async def test_workflow_route_answers_429_when_the_service_refuses(
    request_obj, saturated_service, workflow_crud, formatter
):
    response = await controller.async_workflow_inference(
        request=request_obj,
        workflow_id=uuid.uuid4(),
        payload=WorkflowInferenceRequest(inputs='hello'),
        version=None,
        async_agentic_execution_service=saturated_service,
        workflow_crud_service=workflow_crud,
        response_formatter=formatter,
    )

    assert response.status_code == 429
    assert response.headers['retry-after'] == '45'


async def test_controller_pre_check_answers_429_before_any_lookup(
    request_obj, agent_crud, formatter
):
    """The first gate still short-circuits ahead of the version lookup."""
    service = MagicMock()
    service.queue_is_saturated = AsyncMock(return_value=True)
    service.backpressure_retry_after_seconds = 45
    service.create_and_enqueue_agent = AsyncMock()

    response = await controller.async_agent_inference(
        request=request_obj,
        agent_id=uuid.uuid4(),
        payload=AgentInferenceRequest(inputs='hello'),
        version=None,
        async_agentic_execution_service=service,
        agent_crud_service=agent_crud,
        llm_inference_config_service=MagicMock(),
        response_formatter=formatter,
    )

    assert response.status_code == 429
    assert response.headers['retry-after'] == '45'
    agent_crud.get_agent.assert_not_called()
    service.create_and_enqueue_agent.assert_not_called()


async def test_value_error_still_maps_to_422(request_obj, agent_crud, formatter):
    """The new handler must not shadow the existing one."""
    service = MagicMock()
    service.queue_is_saturated = AsyncMock(return_value=False)
    service.create_and_enqueue_agent = AsyncMock(side_effect=ValueError('bad input'))

    response = await controller.async_agent_inference(
        request=request_obj,
        agent_id=uuid.uuid4(),
        payload=AgentInferenceRequest(inputs='hello'),
        version=None,
        async_agentic_execution_service=service,
        agent_crud_service=agent_crud,
        llm_inference_config_service=MagicMock(),
        response_formatter=formatter,
    )

    assert response.status_code == 422
