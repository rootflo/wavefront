"""The `app_migrations` table: which app migrations this deployment has run."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert

from db_repo_module.database.connection import DatabaseClient
from db_repo_module.models.app_migration import AppMigration

RUNNING, APPLIED, FAILED = 'running', 'applied', 'failed'
# Downgraded: kept for the record, counts as not applied.
REVERTED = 'reverted'


@dataclass(frozen=True)
class LedgerEntry:
    revision: str
    status: str
    applied_by: str
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    error: Optional[str]


class AppMigrationLedger:
    """Each call is its own short transaction, apart from the migration's own."""

    def __init__(self, db_client: DatabaseClient, app_version: Optional[str] = None):
        self._db = db_client
        self._app_version = app_version

    async def table_exists(self) -> bool:
        async with self._db.session() as session:
            found = await session.execute(text("SELECT to_regclass('app_migrations')"))
            return found.scalar() is not None

    async def entries(self) -> Dict[str, LedgerEntry]:
        """Every row by revision; empty while Alembic has not created the table."""
        if not await self.table_exists():
            return {}
        async with self._db.session() as session:
            rows = (await session.execute(select(AppMigration))).scalars().all()
        return {
            row.revision: LedgerEntry(
                revision=row.revision,
                status=row.status,
                applied_by=row.applied_by,
                started_at=row.started_at,
                finished_at=row.finished_at,
                error=row.error,
            )
            for row in rows
        }

    async def mark_running(self, revision: str, description: str, applied_by: str):
        await self._upsert(
            revision,
            description=description,
            status=RUNNING,
            applied_by=applied_by,
            summary=None,
            error=None,
            started_at=func.now(),
            finished_at=None,
        )

    async def mark_applied(self, revision: str, summary: Dict[str, Any]):
        await self._update(revision, status=APPLIED, summary=summary, error=None)

    async def mark_reverted(self, revision: str, summary: Dict[str, Any]):
        await self._update(revision, status=REVERTED, summary=summary, error=None)

    async def mark_failed(self, revision: str, error: str):
        await self._update(revision, status=FAILED, error=error)

    async def stamp(self, revision: str, description: str, applied_by: str):
        """Record a revision as applied without running it."""
        await self._upsert(
            revision,
            description=description,
            status=APPLIED,
            applied_by=applied_by,
            summary=None,
            error=None,
            started_at=func.now(),
            finished_at=func.now(),
        )

    async def delete(self, revision: str) -> bool:
        async with self._db.session() as session:
            result = await session.execute(
                delete(AppMigration).where(AppMigration.revision == revision)
            )
            await session.commit()
        return result.rowcount > 0

    async def _upsert(self, revision: str, **values: Any):
        values['app_version'] = self._app_version
        statement = insert(AppMigration).values(revision=revision, **values)
        statement = statement.on_conflict_do_update(
            index_elements=[AppMigration.revision], set_=values
        )
        async with self._db.session() as session:
            await session.execute(statement)
            await session.commit()

    async def _update(self, revision: str, **values: Any):
        async with self._db.session() as session:
            row = await session.get(AppMigration, revision)
            for key, value in values.items():
                setattr(row, key, value)
            row.finished_at = func.now()
            await session.commit()
