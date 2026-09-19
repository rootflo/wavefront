"""Seeding helpers shared across module test suites.

``create_session`` was copy-pasted into nine test files, seven of them
byte-identical. It lives here now.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.ext.asyncio import async_sessionmaker

    SessionFactory = async_sessionmaker[AsyncSession]


async def seed_user_session(
    session_factory: SessionFactory,
    user_id: str,
    session_id: str,
    *,
    email: str = 'test@example.com',
    first_name: str = 'Test',
    last_name: str = 'User',
    device_info: str = 'test_device',
):
    """Insert the user and login session that an authenticated request needs.

    Returns the ``(user, session)`` pair, both expunged, so callers can read
    their attributes after the session closes.
    """
    from db_repo_module.models.session import Session
    from db_repo_module.models.user import User

    user = User(
        id=user_id,
        email=email,
        password='hashed_password',
        first_name=first_name,
        last_name=last_name,
    )
    db_session = Session(id=session_id, user_id=user_id, device_info=device_info)

    async with session_factory() as session:
        session.add(user)
        session.add(db_session)
        await session.commit()

    return user, db_session


@pytest.fixture
def seed_session(test_session, test_user_id, test_session_id):
    """Callable that seeds the default user/session for this test.

    Tests that just need to be authenticated can ``await seed_session()``
    instead of restating the user and session rows.
    """

    async def _seed(**overrides):
        return await seed_user_session(
            test_session, test_user_id, test_session_id, **overrides
        )

    return _seed
