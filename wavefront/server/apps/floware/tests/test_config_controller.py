from db_repo_module.models.session import Session
from db_repo_module.models.user import User
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def create_session(
    test_session: async_sessionmaker[AsyncSession],
    test_user_id,
    test_session_id,
):
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
async def test_setting_up_credentials_admin(
    test_client,
    test_session: async_sessionmaker[AsyncSession],
    test_user_id,
    test_session_id,
    auth_token,
    mock_admin_functions,
):
    await create_session(test_session, test_user_id, test_session_id)

    response = test_client.put(
        '/floware/v1/settings/config/app-icon',
        headers={'Authorization': f'Bearer {auth_token}'},
        data={'app_config': '{"width":"100px","height":"50px"}'},
        files={'file': open('apps/floware/tests/test.png', 'rb')},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_with_no_admin(
    test_client,
    test_session: async_sessionmaker[AsyncSession],
    test_user_id,
    test_session_id,
    auth_token,
    mock_non_admin_functions,
):
    await create_session(test_session, test_user_id, test_session_id)

    response = test_client.put(
        '/floware/v1/settings/config/app-icon',
        headers={'Authorization': f'Bearer {auth_token}'},
        data={'app_config': '{"width":"100px","height":"50px"}'},
        files={'file': open('apps/floware/tests/test.png', 'rb')},
    )
    print(response.json())
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_without_authorization_header(
    test_client,
    test_session: async_sessionmaker[AsyncSession],
    test_user_id,
    test_session_id,
):
    await create_session(test_session, test_user_id, test_session_id)

    response = test_client.put(
        '/floware/v1/settings/config/app-icon',
        files={'file': open('apps/floware/tests/test.png', 'rb')},
    )
    assert response.status_code == 401


# write test for get config
@pytest.mark.asyncio
async def test_get_config(
    test_client,
    test_session: async_sessionmaker[AsyncSession],
    test_user_id,
    test_session_id,
    auth_token,
    mock_admin_functions,
):
    await create_session(test_session, test_user_id, test_session_id)

    response = test_client.get(
        '/floware/v1/settings/config',
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 200


# write test for get config without authorization header
@pytest.mark.asyncio
async def test_get_config_without_authorization_header(
    test_client,
    test_session: async_sessionmaker[AsyncSession],
    test_user_id,
    test_session_id,
):
    await create_session(test_session, test_user_id, test_session_id)

    response = test_client.get(
        '/floware/v1/settings/config',
    )
    assert response.status_code == 200
