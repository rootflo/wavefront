"""The db/common/auth/user container set that every API test needs.

Assembling these four and wiring them into the right packages was the bulk of
each module's conftest, and the copies had drifted apart. ``core_containers``
builds them once with the standard mocks; modules add their own container on top
and register it for wiring through :meth:`CoreContainers.wire`, which guarantees
the matching ``unwire()`` in teardown.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from dataclasses import field
from typing import Any
from unittest.mock import AsyncMock
from unittest.mock import Mock

import pytest

DEFAULT_CONFIG: dict[str, Any] = {
    'web': {'url': 'http://test.example.com'},
    'auth': {
        'max_failed_attempts': '3',
        'lockout_duration_hours': '24',
        'inactive_days_threshold': '60',
        'password_reset_cooldown_seconds': '60',
        'password_reset_max_per_email': '3',
        'password_reset_rate_window_seconds': '3600',
    },
    'recaptcha': {
        'enabled': 'false',
        'project_id': '',
        'site_key': '',
        'score_threshold': '0.5',
    },
}

RESET_CODE = 'mock_reset_code'
PASSWORD_RESET_PURPOSE = 'password_reset'


def build_cache_manager(user_id: str) -> Mock:
    """Cache stub that answers both the session lookup and the reset-code lookup."""
    cache_manager = Mock()
    session_payload = json.dumps({'user_id': user_id, 'device_info': 'Mozilla/5.0'})
    cache_manager.get_str.side_effect = (
        lambda key: user_id if key == RESET_CODE else session_payload
    )
    # pop_str is GETDEL for single-use reset codes (and related pointers).
    cache_manager.pop_str.side_effect = (
        lambda key, default=None: user_id if key == RESET_CODE else default
    )
    cache_manager.add = Mock(return_value=True)
    cache_manager.incr_with_expiry = Mock(return_value=1)
    return cache_manager


def build_token_service(user_id: str, session_id: str) -> Mock:
    token_service = Mock()
    token_service.create_token.return_value = 'mock_token'
    token_service.decode_token.return_value = {
        'sub': 'test@example.com',
        'user_id': user_id,
        'role_id': 'test_role_id',
        'session_id': session_id,
        'code': RESET_CODE,
        'purpose': PASSWORD_RESET_PURPOSE,
    }
    token_service.token_expiry = 3600
    token_service.temporary_token_expiry = 600
    return token_service


@dataclass
class CoreContainers:
    """The shared containers, plus a wiring registry that always unwires."""

    db_repo: Any
    common: Any
    auth: Any
    user: Any
    db_client: Any
    cache_manager: Mock
    token_service: Mock
    email_send_service: Mock
    user_id: str
    session_id: str
    _wired: list[Any] = field(default_factory=list)

    def wire(self, container: Any, *, packages=None, modules=None) -> Any:
        """Wire a container and remember it, so teardown can undo it.

        Several conftests used to wire containers they never unwired, which left
        dependency_injector overrides in place and made failures depend on test
        order.
        """
        container.wire(packages=packages or [], modules=modules or [])
        self._wired.append(container)
        return container

    def unwire_all(self) -> None:
        while self._wired:
            self._wired.pop().unwire()


@pytest.fixture
def core_containers(db_client, test_user_id, test_session_id, user_config):
    from auth_module.auth_container import AuthContainer
    from common_module.common_container import CommonContainer
    from db_repo_module.db_repo_container import DatabaseModuleContainer
    from user_management_module.user_container import UserContainer

    cache_manager = build_cache_manager(test_user_id)
    token_service = build_token_service(test_user_id, test_session_id)

    db_repo_container = DatabaseModuleContainer()
    db_repo_container.db_client.override(db_client)

    common_container = CommonContainer()
    common_container.cache_manager.override(cache_manager)

    auth_container = AuthContainer(
        db_client=db_client,
        cache_manager=cache_manager,
    )
    auth_container.token_service.override(token_service)
    # Only defined when SUPERSET_FLAG is on, which the plugin defaults to true.
    if hasattr(auth_container, 'superset_service'):
        superset_service = Mock()
        superset_service.generate_guest_token.return_value = 'mock_guest_token'
        auth_container.superset_service.override(superset_service)

    # plugins_module's EmailSendService is handed in by the app rather than
    # constructed by the container, so tests supply the stand-in.
    email_send_service = Mock()
    email_send_service.send = AsyncMock(return_value=True)

    user_container = UserContainer(
        db_client=db_client,
        cache_manager=cache_manager,
        email_send_service=email_send_service,
    )
    user_container.config.override(user_config)

    containers = CoreContainers(
        db_repo=db_repo_container,
        common=common_container,
        auth=auth_container,
        user=user_container,
        db_client=db_client,
        cache_manager=cache_manager,
        token_service=token_service,
        email_send_service=email_send_service,
        user_id=test_user_id,
        session_id=test_session_id,
    )

    yield containers

    containers.unwire_all()


@pytest.fixture
def user_config() -> dict[str, Any]:
    """Config for UserContainer.

    Named for what it configures rather than the generic `mock_config`, which
    several module conftests already use for their own app-level config.
    """
    return DEFAULT_CONFIG
