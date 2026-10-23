"""
Create and update answer 400 with the reason when the YAML sent is not acceptable.

A definition the caller got wrong used to reach the global exception handler and
come back as a generic 500, with the real message only in the server log. The
services now raise ``InvalidDefinitionError`` (a ``ValueError``) for it and the
controllers turn that into a 400. Anything else, such as "already exists", is left
as it was.

The controllers are called directly with their dependencies passed in, which skips
the DI wiring the same way the other tests in this package do.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from common_module.response_formatter import ResponseFormatter

from agents_module.controllers.agent_controller import create_agent, update_agent
from agents_module.controllers.workflow_controller import (
    create_workflow,
    update_workflow,
)
from agents_module.utils.validation_utils import (
    InvalidDefinitionError,
    validate_agent_workflow_name,
)

REASON = (
    "Invalid workflow YAML configuration: Orphan nodes found: ['per_item']. "
    'These nodes have no incoming or outgoing edges.'
)


class FakeRequest:
    headers: dict = {}

    async def body(self):
        return b'arium: {}'


def decode(response):
    return json.loads(response.body)


def service(method, error):
    return SimpleNamespace(**{method: AsyncMock(side_effect=error)})


@pytest.fixture
def formatter():
    return ResponseFormatter()


@pytest.fixture
def tool_loader():
    return Mock(load_all_tools=Mock(return_value=[]))


async def test_create_agent_answers_400_with_the_reason(formatter, tool_loader):
    response = await create_agent(
        request=FakeRequest(),
        name='my-agent',
        namespace='default',
        agent_crud_service=service('create_agent', InvalidDefinitionError(REASON)),
        response_formatter=formatter,
        tool_loader=tool_loader,
    )

    assert response.status_code == 400
    assert decode(response)['meta']['error'] == REASON


async def test_update_agent_answers_400_with_the_reason(formatter, tool_loader):
    response = await update_agent(
        request=FakeRequest(),
        agent_id=uuid4(),
        version=None,
        create_new_version=False,
        agent_crud_service=service('update_agent', InvalidDefinitionError(REASON)),
        response_formatter=formatter,
        tool_loader=tool_loader,
    )

    assert response.status_code == 400
    assert decode(response)['meta']['error'] == REASON


async def test_create_workflow_answers_400_with_the_reason(formatter):
    response = await create_workflow(
        request=FakeRequest(),
        name='my-workflow',
        namespace='default',
        workflow_crud_service=service(
            'create_workflow', InvalidDefinitionError(REASON)
        ),
        response_formatter=formatter,
    )

    assert response.status_code == 400
    assert decode(response)['meta']['error'] == REASON


async def test_update_workflow_answers_400_with_the_reason(formatter):
    response = await update_workflow(
        request=FakeRequest(),
        workflow_id=uuid4(),
        version=None,
        create_new_version=False,
        workflow_crud_service=service(
            'update_workflow', InvalidDefinitionError(REASON)
        ),
        response_formatter=formatter,
    )

    assert response.status_code == 400
    assert decode(response)['meta']['error'] == REASON


async def test_other_value_errors_are_not_turned_into_400(formatter, tool_loader):
    with pytest.raises(ValueError, match='already exists'):
        await create_agent(
            request=FakeRequest(),
            name='my-agent',
            namespace='default',
            agent_crud_service=service(
                'create_agent', ValueError('Agent already exists with name: my-agent')
            ),
            response_formatter=formatter,
            tool_loader=tool_loader,
        )


@pytest.mark.parametrize('name', ['', 'bad name', '-leading-dash', 'new\nline'])
def test_a_bad_name_is_an_invalid_definition(name):
    with pytest.raises(InvalidDefinitionError):
        validate_agent_workflow_name(name)


SECRET = 'connection to db at 10.0.0.5 refused (password=hunter2)'


def agent_crud_service():
    from agents_module.services.agent_crud_service import AgentCrudService

    crud = object.__new__(AgentCrudService)
    crud._check_yaml_content = AsyncMock(return_value=([], {}))
    return crud


def workflow_crud_service(build_error):
    from agents_module.services.workflow_crud_service import WorkflowCrudService

    crud = object.__new__(WorkflowCrudService)
    crud._load_inlined_document = AsyncMock(
        return_value=({'arium': {'agents': [{'name': 'a', 'job': 'x'}]}}, False, [])
    )
    crud._check_document = AsyncMock(return_value=[])
    crud.agent_inference_service = SimpleNamespace(
        create_agent_from_yaml=AsyncMock(side_effect=build_error)
    )
    return crud


async def test_agent_value_error_keeps_its_reason():
    crud = agent_crud_service()
    with patch('agents_module.services.agent_crud_service.AgentBuilder') as builder:
        builder.from_yaml.return_value.build.side_effect = ValueError('bad model')
        with pytest.raises(InvalidDefinitionError, match='bad model'):
            await crud._validate_yaml_content('agent: {}', 'default', 'a', [])


async def test_agent_unexpected_error_does_not_leak_its_message():
    crud = agent_crud_service()
    with patch('agents_module.services.agent_crud_service.AgentBuilder') as builder:
        builder.from_yaml.return_value.build.side_effect = RuntimeError(SECRET)
        with pytest.raises(InvalidDefinitionError) as info:
            await crud._validate_yaml_content('agent: {}', 'default', 'a', [])
    assert str(info.value) == 'Invalid agent YAML configuration: unknown reason'


async def test_workflow_value_error_from_an_inline_agent_keeps_its_reason():
    crud = workflow_crud_service(ValueError('bad model'))
    with pytest.raises(
        InvalidDefinitionError, match='Failed to build inline agent a: bad model'
    ):
        await crud._validate_yaml_content('arium: {}', 'default', 'w')


async def test_workflow_unexpected_error_does_not_leak_its_message():
    crud = workflow_crud_service(RuntimeError(SECRET))
    with pytest.raises(InvalidDefinitionError) as info:
        await crud._validate_yaml_content('arium: {}', 'default', 'w')
    assert str(info.value) == 'Invalid workflow YAML configuration: unknown reason'
