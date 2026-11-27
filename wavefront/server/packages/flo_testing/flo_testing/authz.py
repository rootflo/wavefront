"""A fallback authorization provider for apps built without the middleware.

Several suites mount a router on a bare ``FastAPI()``. Every route now declares
an action, and with no middleware the declaration is enforced by the route's
own dependency, which needs a provider. This one authenticates every request as
the test user and decides with floware's default authorizer, so admin checks
still follow ``patch_is_admin`` and flags follow ``patch_feature_flag``.

An app built with the real middleware (``build_app``) uses its own provider;
this is only the process-wide fallback.
"""

from __future__ import annotations

import pytest

TEST_ROLE_ID = 'test_role_id'


@pytest.fixture(autouse=True)
def authz_fallback_provider(test_user_id, test_session_id):
    from authz_module import AuthzProvider, user_principal
    from authz_module import provider as authz_provider
    from authz_module.default import DefaultAuthorizer
    from authz_module.testing import StaticAuthenticator
    from user_management_module.authorization.legacy_resolver import (
        FlowareLegacyResolver,
    )

    previous = authz_provider.installed()
    provider = AuthzProvider(
        authenticator=StaticAuthenticator(
            user_principal(
                test_user_id, role_id=TEST_ROLE_ID, session_id=test_session_id
            )
        ),
        authorizer=DefaultAuthorizer(FlowareLegacyResolver()),
        name='test-fallback',
    )
    authz_provider.install(provider)
    yield provider
    authz_provider.install(previous)


# Placeholder settings that let a service's routes be imported without its
# infrastructure: nothing connects at import, these only satisfy config.ini.
SERVICE_IMPORT_ENV = {
    'APP_ENV': 'test',
    'APPLICATION_BUCKET': 'authz-snapshot',
    'CLOUD_PROVIDER': 'aws',
    'DB_HOST': 'localhost',
    'DB_NAME': 'authz_snapshot',
    'DB_PASSWORD': 'authz_snapshot',
    'DB_PORT': '5432',
    'DB_USERNAME': 'authz_snapshot',
    'CONSOLE_DB_HOST': 'localhost',
    'CONSOLE_DB_NAME': 'authz_snapshot',
    'CONSOLE_DB_PASSWORD': 'authz_snapshot',
    'CONSOLE_DB_PORT': '5432',
    'CONSOLE_DB_USERNAME': 'authz_snapshot',
    'KMS_ENCRYPTION_KEY': 'authz-snapshot',
    'KMS_SIGNING_KEY': 'authz-snapshot',
    'PASSTHROUGH_SECRET': 'authz-snapshot',
    'RAG_QUEUE': 'authz-snapshot',
    'REDIS_HOST': 'localhost',
    'REDIS_PORT': '6379',
    'REDIS_PROTOCOL': 'redis',
}

UPDATE_ENV_VAR = 'AUTHZ_UPDATE_SNAPSHOT'


def check_authz_snapshot(snapshot_path, target: str, *extra_args: str) -> None:
    """Fail if a service's routes, actions or access matrix moved.

    The snapshot is ``authz snapshot`` output, committed next to the service.
    Any change to who may call what shows up as a diff to it, so it has to be
    regenerated -- and reviewed -- on purpose::

        AUTHZ_UPDATE_SNAPSHOT=1 pytest <this test>

    It runs in a subprocess: importing a service's routes builds its DI
    container, which must not leak into the rest of the test session.
    """
    import json
    import os
    import pathlib
    import subprocess
    import sys

    snapshot_path = pathlib.Path(snapshot_path)
    env = {**SERVICE_IMPORT_ENV, **os.environ}
    # A real AUTHZ_PROVIDER in the developer's shell must not change the result.
    env.pop('AUTHZ_PROVIDER', None)
    result = subprocess.run(
        [sys.executable, '-m', 'authz_module.cli', 'snapshot', target, *extra_args],
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr[-4000:]
    current = json.loads(result.stdout)

    if os.environ.get(UPDATE_ENV_VAR):
        snapshot_path.write_text(json.dumps(current, indent=2, sort_keys=True) + '\n')
        return

    assert (
        snapshot_path.exists()
    ), f'No snapshot at {snapshot_path}; create it with {UPDATE_ENV_VAR}=1'
    committed = json.loads(snapshot_path.read_text())
    assert current['unannotated'] == [], '\n'.join(current['unannotated'])

    changed = sorted(
        key
        for key in set(committed['access']) | set(current['access'])
        if committed['access'].get(key) != current['access'].get(key)
    )
    assert not changed, (
        f'Access changed for {len(changed)} route(s) (regenerate with '
        f'{UPDATE_ENV_VAR}=1 if intended):\n'
        + '\n'.join(
            f'  {key}: {committed["access"].get(key)} -> {current["access"].get(key)}'
            for key in changed[:40]
        )
    )
    assert (
        current['actions'] == committed['actions']
    ), f'The action catalog changed; regenerate with {UPDATE_ENV_VAR}=1 if intended'
    assert (
        current['routes'] == committed['routes']
    ), f'Route declarations changed; regenerate with {UPDATE_ENV_VAR}=1 if intended'
