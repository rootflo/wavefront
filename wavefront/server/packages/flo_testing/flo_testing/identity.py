"""Identity fixtures: the ids a test runs as, and the token it presents."""

from __future__ import annotations

from uuid import uuid4

import pytest


@pytest.fixture
def test_user_id() -> str:
    return str(uuid4())


@pytest.fixture
def test_session_id() -> str:
    return str(uuid4())


@pytest.fixture
def auth_token(core_containers) -> str:
    """Bearer token for the current test user.

    Comes off the mocked token service, so it is only meaningful to the equally
    mocked decode path -- enough to get past RequireAuthMiddleware.
    """
    return core_containers.auth.token_service().create_token(
        sub='test@example.com',
        user_id=core_containers.user_id,
        role_id='test_role_id',
        session_id=core_containers.session_id,
    )


@pytest.fixture
def auth_headers(auth_token) -> dict[str, str]:
    return {'Authorization': f'Bearer {auth_token}'}
