import pytest
from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession
from db_repo_module.models.session import Session
from db_repo_module.models.user import User
from db_repo_module.models.model_schema import ModelSchema
import io
from unittest.mock import Mock
import uuid


async def create_session(test_session: AsyncSession, test_user_id, test_session_id):
    user = User(
        id=test_user_id,
        email='test@example.com',
        password='hashed_password',
        first_name='Test',
        last_name='User',
    )

    # Create a session in the database
    db_session = Session(
        id=test_session_id, user_id=test_user_id, device_info='test_device'
    )

    async with test_session() as session:
        session.add(user)
        session.add(db_session)
        await session.commit()


@pytest.mark.asyncio
async def test_load_model_sucess(
    test_client,
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    auth_token,
    setup_containers,
):
    auth_container, common_container, inference_container = setup_containers
    await create_session(test_session, test_user_id, test_session_id)
    dummy_model_content = b'This is a dummy model file content.'
    cache_manager_mock = Mock()
    # For session data
    cache_manager_mock.get_str.return_value = {}
    cache_manager_mock.add = Mock()
    common_container.cache_manager.override(cache_manager_mock)
    dummy_file = io.BytesIO(dummy_model_content)
    response = test_client.post(
        '/floware/v1/model-repository/model',
        data={'model_type': 'pytorch'},
        files={
            'model_file': ('test_model.pth', dummy_file, 'application/octet-stream')
        },
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_load_model_tensorflow_success(
    test_client,
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    auth_token,
    setup_containers,
):
    auth_container, common_container, inference_container = setup_containers
    await create_session(test_session, test_user_id, test_session_id)
    dummy_model_content = b'This is a dummy tensorflow model file content.'
    dummy_file = io.BytesIO(dummy_model_content)
    cache_manager_mock = Mock()
    # For session data
    cache_manager_mock.get_str.return_value = {}
    cache_manager_mock.add = Mock()
    common_container.cache_manager.override(cache_manager_mock)
    response = test_client.post(
        '/floware/v1/model-repository/model',
        data={'model_type': 'tensorflow'},
        files={'model_file': ('test_model.tf', dummy_file, 'application/octet-stream')},
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 201
    assert (
        response.json()['data']['message']
        == 'Created the model inference table and inserted the model deails successfully'
    )


@pytest.mark.asyncio
async def test_load_model_no_file(
    test_client,
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    auth_token,
):
    await create_session(test_session, test_user_id, test_session_id)
    response = test_client.post(
        '/floware/v1/model-repository/model',
        data={'model_type': 'pytorch'},
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert 'Field required' in response.json()['detail'][0]['msg']


@pytest.mark.asyncio
async def test_list_models_success(
    test_client,
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    auth_token,
    setup_containers,
):
    auth_container, common_container, inference_container = setup_containers

    await create_session(test_session, test_user_id, test_session_id)
    # Insert a dummy model record into the database
    model_id = str(uuid.uuid4())
    model_repo = inference_container.model_inference_repository()
    async with model_repo.session() as session:
        model_record = ModelSchema(
            model_id=model_id,
            model_name='test_model',
            model_path=f'model_{model_id}/test_model.pth',
            model_type='pytorch',
        )
        session.add(model_record)
        await session.commit()
    response = test_client.get(
        '/floware/v1/model-repository/model',
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert len(response.json()['data']['data']) >= 1
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_list_models_with_no_db_entries(
    test_client,
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    auth_token,
    setup_containers,
):
    await create_session(test_session, test_user_id, test_session_id)
    # Insert a dummy model record into the database
    response = test_client.get(
        '/floware/v1/model-repository/model',
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert len(response.json()['data']['data']) == 0


@pytest.mark.asyncio
async def test_list_model_with_id_success(
    test_client,
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    auth_token,
    setup_containers,
):
    auth_container, common_container, inference_container = setup_containers

    await create_session(test_session, test_user_id, test_session_id)
    # Insert a dummy model record into the database
    model_id = str(uuid.uuid4())
    model_repo = inference_container.model_inference_repository()
    async with model_repo.session() as session:
        model_record = ModelSchema(
            model_id=model_id,
            model_name='test_model',
            model_path=f'model_{model_id}/test_model.pth',
            model_type='pytorch',
        )
        session.add(model_record)
        await session.commit()
    response = test_client.get(
        f'/floware/v1/model-repository/model/{model_id}',
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert str(response.json()['data']['data']['model_id']) == str(model_id)
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_list_model_with_id_failure(
    test_client,
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    auth_token,
    setup_containers,
):
    auth_container, common_container, inference_container = setup_containers

    await create_session(test_session, test_user_id, test_session_id)
    # Insert a dummy model record into the database
    model_id = str(uuid.uuid4())
    response = test_client.get(
        f'/floware/v1/model-repository/model/{model_id}',
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert (
        response.json()['meta']['error']
        == 'Model details not found in the Model inference table'
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
