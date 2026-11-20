"""Floconsole login re-checks the account after bcrypt and signing.

Both run off the event loop, so a password change or an account disable can
land in between. The login must then be refused, and no session created.
"""

import importlib
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from common_module.blocking_io import shutdown_blocking_io

# Importing floconsole.di runs create_container(), which needs the full
# deployment environment. Register the package without its __init__ so the
# controller can import the container class it uses for Provide markers.
_di_dir = Path(__file__).resolve().parents[1] / 'floconsole' / 'di'
if 'floconsole.di' not in sys.modules:
    _pkg = types.ModuleType('floconsole.di')
    _pkg.__path__ = [str(_di_dir)]
    sys.modules['floconsole.di'] = _pkg

auth_controller = importlib.import_module('floconsole.controllers.auth_controller')
from floconsole.utils.password_utils import hash_password  # noqa: E402

PASSWORD = 'Correct@123'


@pytest.fixture(autouse=True)
def fresh_pools():
    yield
    shutdown_blocking_io()


def user(password_hash, deleted=False):
    return SimpleNamespace(
        id='u1', email='a@b.c', password=password_hash, deleted=deleted
    )


def formatter():
    return MagicMock(
        buildSuccessResponse=lambda data: {'data': data},
        buildErrorResponse=lambda error: {'error': error},
    )


async def login(found, current):
    """Run authenticate with the user read before verification (``found``) and
    the one read again right before the session is created (``current``)."""
    user_repository = MagicMock(find_one=AsyncMock(side_effect=[found, current]))
    session_repository = MagicMock(delete_all=AsyncMock(), create=AsyncMock())
    token_service = MagicMock(
        create_token_async=AsyncMock(return_value='jwt'), token_expiry=3600
    )
    request = MagicMock(headers={'User-Agent': 'ua'})

    response = await auth_controller.authenticate(
        request=request,
        auth_data=auth_controller.AuthRequest(email='a@b.c', password=PASSWORD),
        token_service=token_service,
        user_repository=user_repository,
        session_repository=session_repository,
        response_formatter=formatter(),
    )
    return response, session_repository


async def test_unchanged_account_logs_in():
    hashed = hash_password(PASSWORD)

    response, sessions = await login(user(hashed), user(hashed))

    assert response.status_code == 200
    sessions.delete_all.assert_awaited_once()
    sessions.create.assert_awaited_once()


@pytest.mark.parametrize(
    'current',
    [
        None,
        'password-changed',
        'disabled',
    ],
)
async def test_account_changed_during_login_is_refused(current):
    hashed = hash_password(PASSWORD)
    now = {
        None: None,
        'password-changed': user(hash_password('Other@456')),
        'disabled': user(hashed, deleted=True),
    }[current]

    response, sessions = await login(user(hashed), now)

    assert response.status_code == 403
    sessions.delete_all.assert_not_awaited()
    sessions.create.assert_not_awaited()
