"""The check floware's lifespan runs: refuse to serve while a blocking migration is due."""

from __future__ import annotations

from common_module.feature.feature_flag import FeatureFlags
from common_module.log.logger import logger
from db_repo_module.database.connection import DatabaseClient
from floware.app_migrations.ledger import AppMigrationLedger
from floware.app_migrations.registry import load_migrations
from floware.app_migrations.runner import (
    APPLIED,
    NOT_APPLICABLE,
    migration_states,
    pending_blocking,
)


class AppMigrationPendingError(RuntimeError):
    pass


async def check_app_migrations(db_client: DatabaseClient, flags: FeatureFlags) -> None:
    """Raise if a blocking app migration applies here and is not applied.

    Non-blocking ones are logged. Runs after Alembic, so the ledger table exists.
    """
    scripts = load_migrations()
    entries = await AppMigrationLedger(db_client).entries()

    blocking = pending_blocking(scripts, entries, flags)
    if blocking:
        names = ', '.join(f'{s.revision} ({s.description})' for s in blocking)
        verb = 'migration {} has' if len(blocking) == 1 else 'migrations {} have'
        raise AppMigrationPendingError(f'App {verb.format(names)} not been applied')

    for state in migration_states(scripts, entries, flags):
        if state.state not in (APPLIED, NOT_APPLICABLE):
            logger.warning(
                f'App migration {state.script.revision} '
                f'({state.script.description}) is {state.state}'
            )
