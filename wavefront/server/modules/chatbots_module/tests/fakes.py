"""Test doubles for the repository's session escape hatch.

`create_session` opens a real AsyncSession via `repository.session()` so the
session row and its welcome message land in one transaction, which means it
cannot be exercised through a plain AsyncMock on the repository.
"""

import uuid
from unittest.mock import MagicMock


class FakeDbSession:
    """Records what a unit of work added, flushed and committed."""

    def __init__(
        self,
        commit_error: Exception | None = None,
        flush_error: Exception | None = None,
    ):
        self.added: list = []
        self.flushes = 0
        self.commits = 0
        self.refreshed: list = []
        self.rolled_back = False
        self._commit_error = commit_error
        self._flush_error = flush_error

    async def __aenter__(self) -> 'FakeDbSession':
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        # SQLAlchemy discards an uncommitted transaction when the session
        # closes; record that so a test can assert nothing was persisted.
        if exc_type is not None and self.commits == 0:
            self.rolled_back = True
        return False

    def add(self, instance) -> None:
        self.added.append(instance)

    async def flush(self) -> None:
        self.flushes += 1
        if self._flush_error is not None:
            raise self._flush_error
        # Only the primary key is emulated, because that is the one
        # flush-assigned value create_session depends on: the welcome message
        # needs session.id for its foreign key.
        for instance in self.added:
            if getattr(instance, 'id', None) is None:
                instance.id = uuid.uuid4()

    async def commit(self) -> None:
        if self._commit_error is not None:
            raise self._commit_error
        self.commits += 1

    async def refresh(self, instance) -> None:
        self.refreshed.append(instance)

    def added_of(self, model) -> list:
        return [instance for instance in self.added if isinstance(instance, model)]


def repository_with_session(db_session: FakeDbSession) -> MagicMock:
    """A repository stub whose `.session()` yields `db_session`.

    Deliberately a MagicMock, not an AsyncMock: `session()` is called and then
    entered as an async context manager, so it must return the manager itself
    rather than a coroutine.
    """
    repository = MagicMock()
    repository.session = MagicMock(return_value=db_session)
    return repository
