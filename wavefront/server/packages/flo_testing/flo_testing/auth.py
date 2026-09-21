"""Patching the caller's identity for controller tests.

``get_current_user`` and ``check_is_admin`` are imported into each controller's
own namespace, so they have to be patched there rather than at their definition
site -- often in two namespaces at once, because the read paths reach
``check_is_admin`` through ``user_utils.can_read_users`` instead. That detail is
why every conftest grew its own pile of near-identical monkeypatch fixtures.

The two are patched separately because tests compose them: a test may want a
real-looking admin check but a deliberately wrong ``role_id``. ``patch_auth``
does both at once for the common case.

Note the real ``user_utils.get_current_user`` is sync and returns
``(role_id, user_id, session_id)`` -- role first.
"""

from __future__ import annotations

import pytest

USER_UTILS = 'user_management_module.utils.user_utils'


def _targets(namespaces, include_user_utils):
    targets = list(namespaces)
    if include_user_utils and USER_UTILS not in targets:
        targets.append(USER_UTILS)
    return targets


@pytest.fixture
def patch_current_user(monkeypatch, test_user_id, test_session_id):
    """Patch ``get_current_user`` in the given controller namespaces."""

    def _patch(
        *namespaces: str,
        role_id: str = 'test_role_id',
        user_id: str | None = None,
        session_id: str | None = None,
        include_user_utils: bool = True,
    ) -> None:
        resolved_user_id = test_user_id if user_id is None else user_id
        resolved_session_id = test_session_id if session_id is None else session_id

        def fake_get_current_user(request):
            return role_id, resolved_user_id, resolved_session_id

        for namespace in _targets(namespaces, include_user_utils):
            # raising=False: not every namespace imports the helper.
            monkeypatch.setattr(
                f'{namespace}.get_current_user',
                fake_get_current_user,
                raising=False,
            )

    return _patch


@pytest.fixture
def patch_is_admin(monkeypatch):
    """Patch ``check_is_admin`` in the given controller namespaces."""

    def _patch(
        *namespaces: str,
        is_admin: bool = True,
        include_user_utils: bool = True,
    ) -> None:
        async def fake_check_is_admin(role_id, role_repository=None):
            return is_admin

        for namespace in _targets(namespaces, include_user_utils):
            monkeypatch.setattr(
                f'{namespace}.check_is_admin',
                fake_check_is_admin,
                raising=False,
            )

    return _patch


@pytest.fixture
def patch_auth(patch_current_user, patch_is_admin):
    """Patch both identity and the admin check -- the usual case."""

    def _patch(
        *namespaces: str,
        is_admin: bool = True,
        role_id: str = 'test_role_id',
        user_id: str | None = None,
        session_id: str | None = None,
        include_user_utils: bool = True,
    ) -> None:
        patch_current_user(
            *namespaces,
            role_id=role_id,
            user_id=user_id,
            session_id=session_id,
            include_user_utils=include_user_utils,
        )
        patch_is_admin(
            *namespaces,
            is_admin=is_admin,
            include_user_utils=include_user_utils,
        )

    return _patch


@pytest.fixture
def patch_feature_flag(monkeypatch):
    """Force ``is_feature_enabled`` in a controller's namespace on or off."""

    def _patch(namespace: str, enabled: bool) -> None:
        monkeypatch.setattr(
            f'{namespace}.is_feature_enabled',
            lambda flag: enabled,
            raising=False,
        )

    return _patch
