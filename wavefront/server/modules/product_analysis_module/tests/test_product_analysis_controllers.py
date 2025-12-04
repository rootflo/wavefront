from db_repo_module.models.session import Session
from db_repo_module.models.user import User
import pytest
from sqlalchemy.ext.asyncio import AsyncSession


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


@pytest.fixture
def payload():
    return {
        'event_name': 'button_click',
        'type': 'interaction',
        'sub_type': 'cta_click',
        'category': 'user_engagement',
        'sub_category': 'homepage',
        'action': 'click',
        'action_type': 'primary',
        'page': 'home',
        'page_path': '/home',
        'matadata': {
            'button_id': 'signup-btn',
            'timestamp': '2025-08-11T15:45:00Z',
            'device': 'desktop',
            'browser': 'Chrome',
            'experiment_variant': 'A',
        },
    }


@pytest.mark.asyncio
async def test_post_product_analysis(
    test_client,
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    auth_token,
    payload,
):
    await create_session(test_session, test_user_id, test_session_id)
    response = test_client.post(
        '/floware/v1/product-analysis',
        json=payload,
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    print(response.json())
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_post_product_analysis_invalid_token(
    test_client,
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    payload,
    setup_containers,
):
    # override the token service
    auth_container, _, _ = setup_containers
    token_service = auth_container.token_service()
    token_service.decode_token.return_value = {}
    auth_container.token_service.override(token_service)

    await create_session(test_session, test_user_id, test_session_id)
    response = test_client.post(
        '/floware/v1/product-analysis',
        json=payload,
        headers={'Authorization': 'Bearer 12323'},
    )
    print(response.json())
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_post_product_analysis_with_invalid_payload(
    test_client,
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    payload,
    setup_containers,
):
    await create_session(test_session, test_user_id, test_session_id)
    response = test_client.post(
        '/floware/v1/product-analysis',
        json={
            'event_name': 'button_click',
        },
        headers={'Authorization': 'Bearer 12323'},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_post_product_analysis_with_valid_payload(
    test_client,
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    payload,
    setup_containers,
):
    await create_session(test_session, test_user_id, test_session_id)
    response = test_client.post(
        '/floware/v1/product-analysis',
        json=payload,
        headers={'Authorization': 'Bearer 12323'},
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_post_product_analysis_with_minimal_payload(
    test_client,
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    setup_containers,
):
    """Test POST endpoint with minimal required payload"""
    await create_session(test_session, test_user_id, test_session_id)

    minimal_payload = {'event_name': 'page_view', 'page': 'home', 'page_path': '/home'}

    response = test_client.post(
        '/floware/v1/product-analysis',
        json=minimal_payload,
        headers={'Authorization': 'Bearer 12323'},
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_post_product_analysis_with_null_optional_fields(
    test_client,
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    setup_containers,
):
    """Test POST endpoint with null values for optional fields"""
    await create_session(test_session, test_user_id, test_session_id)

    payload_with_nulls = {
        'event_name': 'button_click',
        'type': None,
        'sub_type': None,
        'category': None,
        'sub_category': None,
        'action': None,
        'action_type': None,
        'page': 'home',
        'page_path': '/home',
        'matadata': None,
    }

    response = test_client.post(
        '/floware/v1/product-analysis',
        json=payload_with_nulls,
        headers={'Authorization': 'Bearer 12323'},
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_post_product_analysis_with_special_characters(
    test_client,
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    setup_containers,
):
    """Test POST endpoint with special characters in event data"""
    await create_session(test_session, test_user_id, test_session_id)

    special_char_payload = {
        'event_name': 'form_submit_&_validate',
        'type': 'interaction',
        'sub_type': 'form_complete',
        'category': 'conversion',
        'sub_category': 'signup_flow',
        'action': 'submit',
        'action_type': 'primary',
        'page': 'signup-page',
        'page_path': '/signup?utm_source=google&utm_medium=cpc',
        'matadata': {
            'form_name': 'user_registration_form',
            'special_chars': 'test@example.com',
            'unicode_text': 'café résumé naïve',
            'html_entities': "&lt;script&gt;alert('test')&lt;/script&gt;",
        },
    }

    response = test_client.post(
        '/floware/v1/product-analysis',
        json=special_char_payload,
        headers={'Authorization': 'Bearer 12323'},
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_post_product_analysis_with_large_metadata(
    test_client,
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    setup_containers,
):
    """Test POST endpoint with large metadata payload"""
    await create_session(test_session, test_user_id, test_session_id)

    large_metadata = {
        'event_name': 'user_session',
        'type': 'session',
        'sub_type': 'session_start',
        'category': 'user_engagement',
        'sub_category': 'session_tracking',
        'action': 'start',
        'action_type': 'automatic',
        'page': 'dashboard',
        'page_path': '/dashboard',
        'matadata': {
            'session_id': 'sess_' + 'x' * 100,
            'user_preferences': {
                'theme': 'dark',
                'language': 'en-US',
                'timezone': 'America/New_York',
                'notifications': {'email': True, 'push': False, 'sms': True},
            },
            'browser_details': {
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'language': 'en-US,en;q=0.9',
                'platform': 'Win32',
                'cookie_enabled': True,
                'do_not_track': False,
            },
            'performance_metrics': {
                'page_load_time': 1250,
                'dom_content_loaded': 850,
                'first_contentful_paint': 1200,
                'largest_contentful_paint': 1800,
                'cumulative_layout_shift': 0.05,
            },
            'analytics_data': {
                'ga_client_id': '123456789.1234567890',
                'gtm_container_id': 'GTM-XXXXXXX',
                'custom_dimensions': {
                    'cd1': 'premium_user',
                    'cd2': 'mobile_device',
                    'cd3': 'returning_visitor',
                },
            },
        },
    }

    response = test_client.post(
        '/floware/v1/product-analysis',
        json=large_metadata,
        headers={'Authorization': 'Bearer 12323'},
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_get_product_analysis_as_admin(
    test_client,
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    auth_token,
    mock_admin_functions,
):
    await create_session(test_session, test_user_id, test_session_id)

    response = test_client.get(
        '/floware/v1/product-analysis',
        headers={'Authorization': f'Bearer {auth_token}'},
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_product_analysis_unauthorized(
    test_client, test_session: AsyncSession, test_user_id, test_session_id
):
    """Test GET endpoint without authorization token"""
    await create_session(test_session, test_user_id, test_session_id)

    response = test_client.get('/floware/v1/product-analysis')

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_product_analysis_invalid_token(
    test_client,
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    setup_containers,
):
    """Test GET endpoint with invalid authorization token"""
    await create_session(test_session, test_user_id, test_session_id)

    # Override the token service to return invalid token
    auth_container, _, _ = setup_containers
    token_service = auth_container.token_service()
    token_service.decode_token.return_value = {}
    auth_container.token_service.override(token_service)

    response = test_client.get(
        '/floware/v1/product-analysis',
        headers={'Authorization': 'Bearer invalid_token_123'},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_product_analysis_with_query_params(
    test_client,
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    auth_token,
    mock_admin_functions,
):
    """Test GET endpoint with query parameters for filtering"""
    await create_session(test_session, test_user_id, test_session_id)

    # Test with various query parameters
    query_params = {
        'page': 1,
        'size': 10,
        'event_name': 'button_click',
        'page_path': '/home',
        'start_date': '2025-01-01',
        'end_date': '2025-12-31',
    }

    response = test_client.get(
        '/floware/v1/product-analysis',
        params=query_params,
        headers={'Authorization': f'Bearer {auth_token}'},
    )

    assert response.status_code == 200
    # Verify response structure
    response_data = response.json()
    assert isinstance(response_data, dict)
