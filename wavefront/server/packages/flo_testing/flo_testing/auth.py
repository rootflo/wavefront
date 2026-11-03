"""Patching the caller's identity for controller tests.

``get_current_user`` is imported into each controller's own namespace, so it has
to be patched there rather than at its definition site.

``check_is_admin`` is no longer called by controllers: routes declare an action
and the default authorizer's legacy resolver asks
``user_utils.check_is_admin``, looked up on the module at call time. Patching it
in ``user_utils`` (which ``include_user_utils`` does by default) decides every
admin rule; the per-controller patches are kept for callers that still pass
controller namespaces and are harmless no-ops.

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

        # user_utils always: it is where the default authorizer asks, so it is
        # what decides every admin rule. include_user_utils is ignored here.
        del include_user_utils
        for namespace in _targets(namespaces, True):
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
def patch_feature_flag(core_containers):
    """Turn every feature flag on or off for this test.

    ``namespace`` is unused. Callers used to patch ``is_feature_enabled`` in one
    module; flags are now one injected object, so the override covers every
    caller.
    """

    def _patch(namespace: str, enabled: bool) -> None:
        del namespace
        from dependency_injector import providers

        from common_module.feature.feature_flag import FeatureFlags

        core_containers.common.feature_flags.override(
            providers.Object(
                FeatureFlags(
                    allow_non_admin_all_data_access=enabled,
                    datasource_audit_enabled=enabled,
                    datasource_change_notification=enabled,
                    inactive_account_disable=enabled,
                    superset=enabled,
                )
            )
        )

    return _patch
