import csv
import json
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from apscheduler.triggers.cron import CronTrigger
from common_module.log.logger import logger
from common_module.utils.serializer import serialize_values
from datasource import DatasourcePlugin
from db_repo_module.database.connection import DatabaseClient
from db_repo_module.models.datasource import Datasource
from db_repo_module.models.dynamic_query_yaml import DynamicQueryYaml
from db_repo_module.models.scheduled_job import ScheduledJob
from db_repo_module.models.scheduled_job_execution import ScheduledJobExecution
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from plugins_module.services.dynamic_query_service import DynamicQueryService
from plugins_module.services.datasource_services import get_datasource_config
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from user_management_module.services.email_service import EmailService

STALE_LOCK_TIMEOUT_MINUTES = 30
SIGNED_URL_EXPIRY_SECONDS = 7 * 24 * 60 * 60


class ScheduledJobService:
    def __init__(
        self,
        db_client: DatabaseClient,
        scheduled_job_repository: SQLAlchemyRepository[ScheduledJob],
        scheduled_job_execution_repository: SQLAlchemyRepository[ScheduledJobExecution],
        datasource_repository: SQLAlchemyRepository[Datasource],
        dynamic_query_repository: SQLAlchemyRepository[DynamicQueryYaml],
        cloud_storage_manager,
        bucket_name: str,
        email_service: EmailService,
    ):
        self.db_client = db_client
        self.scheduled_job_repository = scheduled_job_repository
        self.scheduled_job_execution_repository = scheduled_job_execution_repository
        self.datasource_repository = datasource_repository
        self.dynamic_query_repository = dynamic_query_repository
        self.cloud_storage_manager = cloud_storage_manager
        self.bucket_name = bucket_name
        self.email_service = email_service
        self.worker_id = os.getenv('HOSTNAME', 'floware-worker')
        self.dynamic_query_service = DynamicQueryService(
            cloud_storage_manager=self.cloud_storage_manager,
            dynamic_query_repo=self.dynamic_query_repository,
            bucket_name=self.bucket_name,
        )

    def _resolve_runtime_params(self, payload: dict, tz_name: str) -> dict | None:
        """Build query params for this run, including dynamic date presets."""
        base_params = payload.get('params')
        params: dict = dict(base_params) if isinstance(base_params, dict) else {}
        date_range = payload.get('date_range')
        if date_range not in {'last_day', 'last_7_days', 'last_30_days'}:
            return params or None

        tz = ZoneInfo(tz_name)
        today = datetime.now(tz).date()
        if date_range == 'last_day':
            start_date = today - timedelta(days=1)
            end_date = today - timedelta(days=1)
        elif date_range == 'last_7_days':
            end_date = today - timedelta(days=1)
            start_date = end_date - timedelta(days=6)
        else:  # last_30_days
            end_date = today - timedelta(days=1)
            start_date = end_date - timedelta(days=29)

        start_key = payload.get('start_date_param', 'start_date')
        end_key = payload.get('end_date_param', 'end_date')
        params[str(start_key)] = start_date.isoformat()
        params[str(end_key)] = end_date.isoformat()
        return params

    def _compute_next_run_at(self, cron_expr: str, tz_name: str) -> datetime:
        tz = ZoneInfo(tz_name)
        now = datetime.now(tz)
        trigger = CronTrigger.from_crontab(cron_expr, timezone=tz)
        next_fire = trigger.get_next_fire_time(previous_fire_time=None, now=now)
        if next_fire is None:
            raise ValueError('Unable to compute next run time for cron expression')
        # Normalise to UTC-aware so the value written to the TIMESTAMPTZ column is
        # always unambiguous regardless of the PostgreSQL session timezone.
        return next_fire.astimezone(timezone.utc)

    async def create_job(
        self,
        job_type: str,
        cron_expr: str,
        timezone_name: str,
        payload: dict,
        max_retries: int,
    ) -> ScheduledJob:
        next_run_at = self._compute_next_run_at(cron_expr, timezone_name)
        return await self.scheduled_job_repository.create(
            job_type=job_type,
            cron_expr=cron_expr,
            timezone=timezone_name,
            payload=payload,
            next_run_at=next_run_at,
            status='active',
            max_retries=max_retries,
            retry_count=0,
        )

    async def list_jobs(
        self,
        limit: int = 100,
        job_type: str | None = None,
        status: str | None = None,
        payload_filters: dict[str, str] | None = None,
    ) -> list[ScheduledJob]:
        query = select(ScheduledJob)
        if job_type:
            query = query.where(ScheduledJob.job_type == job_type)
        if status:
            query = query.where(ScheduledJob.status == status)
        if payload_filters:
            for key, value in payload_filters.items():
                # JSONB subscript + astext for case-sensitive text comparison.
                query = query.where(ScheduledJob.payload[key].astext == value)
        query = query.order_by(ScheduledJob.created_at.desc()).limit(limit)
        async with self.db_client.session() as session:
            return (await session.scalars(query)).all()

    async def get_job(self, job_id: str) -> ScheduledJob | None:
        return await self.scheduled_job_repository.find_one(id=job_id)

    async def update_job(
        self,
        job_id: str,
        cron_expr: str | None = None,
        timezone_name: str | None = None,
        payload: dict | None = None,
        max_retries: int | None = None,
        status: str | None = None,
    ) -> ScheduledJob | None:
        updates = {}
        job = await self.scheduled_job_repository.find_one(id=job_id)
        if not job:
            return None

        effective_cron = cron_expr or job.cron_expr
        effective_tz = timezone_name or job.timezone
        if cron_expr or timezone_name:
            updates['next_run_at'] = self._compute_next_run_at(
                effective_cron, effective_tz
            )
            updates['cron_expr'] = effective_cron
            updates['timezone'] = effective_tz

        if payload is not None:
            updates['payload'] = payload
        if max_retries is not None:
            updates['max_retries'] = max_retries
        if status is not None:
            updates['status'] = status

        if updates:
            return await self.scheduled_job_repository.find_one_and_update(
                filters={'id': job_id}, refresh=True, **updates
            )
        return job

    async def pause_job(self, job_id: str) -> ScheduledJob | None:
        return await self.scheduled_job_repository.find_one_and_update(
            filters={'id': job_id}, refresh=True, status='paused'
        )

    async def resume_job(self, job_id: str) -> ScheduledJob | None:
        job = await self.scheduled_job_repository.find_one(id=job_id)
        if not job:
            return None
        return await self.scheduled_job_repository.find_one_and_update(
            filters={'id': job_id},
            refresh=True,
            status='active',
            next_run_at=self._compute_next_run_at(job.cron_expr, job.timezone),
        )

    async def delete_job(self, job_id: str) -> bool:
        await self.scheduled_job_repository.delete_all(id=job_id)
        return True

    async def claim_due_jobs(self, batch_size: int = 10) -> list[dict]:
        claim_sql = text(
            """
            WITH due AS (
                SELECT id
                FROM scheduled_job
                WHERE status = 'active'
                  AND next_run_at <= now()
                ORDER BY next_run_at ASC
                FOR UPDATE SKIP LOCKED
                LIMIT :batch_size
            )
            UPDATE scheduled_job sj
            SET status = 'running',
                locked_by = :worker_id,
                locked_at = now(),
                updated_at = now()
            FROM due
            WHERE sj.id = due.id
            RETURNING sj.id, sj.job_type, sj.payload, sj.cron_expr, sj.timezone, sj.next_run_at, sj.retry_count, sj.max_retries
            """
        )
        async with self.db_client.session() as session:
            async with session.begin():
                res = await session.execute(
                    claim_sql,
                    {'batch_size': batch_size, 'worker_id': self.worker_id},
                )
                rows = [dict(row._mapping) for row in res.fetchall()]
            return rows

    async def _unlock_job(
        self,
        job_id: str,
        status: str,
        retry_count: int,
        last_error: str | None,
        next_run_at: datetime,
    ):
        """Unconditionally release the row-level lock on a job. Must never throw."""
        try:
            await self.scheduled_job_repository.find_one_and_update(
                filters={'id': job_id},
                refresh=False,
                status=status,
                retry_count=retry_count,
                last_error=last_error,
                last_run_at=datetime.now(timezone.utc),
                next_run_at=next_run_at,
                locked_by=None,
                locked_at=None,
            )
        except Exception as unlock_exc:
            logger.error(
                f'CRITICAL: failed to unlock job {job_id} after execution: {unlock_exc}'
            )

    async def _create_execution_lock(
        self, job_id: str, scheduled_for: datetime
    ) -> tuple[bool, str]:
        execution_key = f'{job_id}:{scheduled_for.isoformat()}'
        try:
            await self.scheduled_job_execution_repository.create(
                scheduled_job_id=job_id,
                execution_key=execution_key,
                scheduled_for=scheduled_for,
                status='running',
            )
            return True, execution_key
        except IntegrityError:
            # Unique constraint hit — another worker already claimed this fire time.
            logger.info(f'Skipping duplicate execution for job={job_id}')
            return False, execution_key
        except Exception as exc:
            # Real DB error — re-raise so the job is not silently skipped.
            logger.error(
                f'Unexpected error creating execution lock for job={job_id}: {exc}'
            )
            raise

    async def _complete_execution(
        self, execution_key: str, status: str, error: str | None = None
    ):
        try:
            await self.scheduled_job_execution_repository.find_one_and_update(
                filters={'execution_key': execution_key},
                status=status,
                error=error,
                refresh=False,
            )
        except Exception as exc:
            logger.error(
                f'Failed to update execution record key={execution_key}: {exc}'
            )

    async def recover_stale_locks(self):
        """Reset jobs stuck in 'running' and remove their orphaned in-progress execution locks.

        A crashed worker leaves the scheduled_job row in 'running' and the
        scheduled_job_execution row in 'running' (never completed).  If we only
        reset the job row the next claim hits the unique constraint on
        (scheduled_job_id, scheduled_for) and skips the fire.  Both cleanups
        must happen atomically.
        """
        recover_sql = text(
            """
            WITH stale AS (
                UPDATE scheduled_job
                SET status = 'active',
                    locked_by = NULL,
                    locked_at = NULL,
                    updated_at = now()
                WHERE status = 'running'
                  AND locked_at <= now() - make_interval(mins => :timeout_minutes)
                RETURNING id
            ),
            cleaned AS (
                DELETE FROM scheduled_job_execution
                WHERE scheduled_job_id IN (SELECT id FROM stale)
                  AND status = 'running'
                RETURNING scheduled_job_id
            )
            SELECT
                (SELECT count(*) FROM stale)   AS recovered_jobs,
                (SELECT count(*) FROM cleaned) AS cleaned_executions
            """
        )
        try:
            async with self.db_client.session() as session:
                async with session.begin():
                    res = await session.execute(
                        recover_sql,
                        {'timeout_minutes': STALE_LOCK_TIMEOUT_MINUTES},
                    )
                    row = res.fetchone()
                    recovered = int(row.recovered_jobs) if row else 0
                    cleaned = int(row.cleaned_executions) if row else 0
            if recovered:
                logger.warning(
                    f'Recovered {recovered} stale locked job(s); '
                    f'removed {cleaned} orphaned execution lock(s)'
                )
        except Exception as exc:
            logger.error(f'Failed to recover stale locks: {exc}')

    def recover_stale_locks_sync(self):
        import asyncio

        asyncio.run(self.recover_stale_locks())

    async def _execute_email_dynamic_query_job(self, payload: dict, job_timezone: str):
        datasource_id = payload.get('datasource_id')
        query_id = payload.get('query_id')
        recipients = payload.get('recipients', [])
        subject = payload.get('subject', f'Scheduled Dynamic Query Report: {query_id}')
        filter_expr = payload.get('filter')
        offset = payload.get('offset', 0)
        limit = payload.get('limit', 100)
        params = self._resolve_runtime_params(payload, job_timezone)

        if isinstance(recipients, str):
            recipients = [recipients]

        if not datasource_id or not query_id or not recipients:
            raise ValueError('payload must include datasource_id, query_id, recipients')

        datasource_type, datasource_config = await get_datasource_config(
            datasource_id=datasource_id,
            datasource_repository=self.datasource_repository,
        )
        if not datasource_type or not datasource_config:
            raise ValueError(f'Datasource not found: {datasource_id}')

        yaml_query, yaml_name = await self.dynamic_query_service.get_dynamic_yaml_query(
            query_id
        )
        if not yaml_query:
            raise ValueError(f'Dynamic query not found: {query_id}')
        datasource_plugin = DatasourcePlugin(datasource_type, datasource_config)
        result = await datasource_plugin.execute_dynamic_query(
            yaml_query,
            None,
            filter_expr,
            offset,
            limit,
            params,
        )
        result = serialize_values(result)
        if not result:
            raise ValueError(f'No results returned for dynamic query: {query_id}')
        first_key = next(iter(result))
        if result[first_key].get('status') != 'success':
            raise ValueError(
                f'Unexpected dynamic query result format for query_id {query_id}, no successful results'
            )

        rows = result[first_key].get('result') or []
        if not isinstance(rows, list):
            raise ValueError(
                f'Unexpected dynamic query result format for query_id {query_id}, invalid rows'
            )

        if rows:
            fieldnames = list(rows[0].keys())
            for row in rows[1:]:
                for k in row:
                    if k not in fieldnames:
                        fieldnames.append(k)
        else:
            fieldnames = []

        def _cell_value(v):
            if isinstance(v, (dict, list)):
                return json.dumps(v)
            return v if v is None or isinstance(v, str) else str(v)

        report_filename = f'{query_id}_{datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")}_report.csv'
        report_key = f'scheduled_query_reports/{query_id}/{report_filename}'
        # Store report CSV in cloud storage and share via signed URL (10 days).
        with self.cloud_storage_manager.open_text_writer(
            bucket_name=self.bucket_name, key=report_key, content_type='text/csv'
        ) as f:
            if fieldnames:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
                writer.writeheader()
                for row in rows:
                    writer.writerow({k: _cell_value(row.get(k)) for k in fieldnames})
        report_url = self.cloud_storage_manager.generate_presigned_url(
            bucket_name=self.bucket_name,
            key=report_key,
            type='GET',
            expiresIn=SIGNED_URL_EXPIRY_SECONDS,
        )
        body = (
            f'<p>Scheduled report: <b>{yaml_name or query_id}</b></p>'
            f'<p>Datasource: {datasource_id}</p>'
            '<p>Report generated successfully.</p>'
            f'<p><a href="{report_url}" target="_blank" rel="noopener noreferrer">'
            'Download report (valid for 7 days)</a></p>'
        )

        failed_recipients = []
        for recipient in recipients:
            is_sent = self.email_service.send_email(
                subject,
                body,
                recipient,
            )
            if not is_sent:
                failed_recipients.append(recipient)

        if failed_recipients:
            if len(failed_recipients) == len(recipients):
                # Every send failed — no one has the report, so raising here is
                # safe: the next-run retry will resend to all recipients without
                # creating duplicates.
                raise ValueError(
                    f'Failed sending report to all {len(recipients)} recipient(s) '
                    f'for query={query_id}'
                )
            # Partial failure: some recipients already have the report.  Do NOT
            # raise — that would schedule a retry which re-sends to the
            # already-successful recipients.  Log the failures so they are
            # visible in job.last_error via the caller, but let execution
            # complete normally.
            logger.error(
                f'Partial delivery failure for query={query_id}: '
                f'{len(failed_recipients)}/{len(recipients)} recipient(s) failed: '
                f'{", ".join(failed_recipients)}'
            )

    async def _run_job(self, job_row: dict):
        job_id = str(job_row['id'])
        scheduled_for = job_row['next_run_at']
        acquired, execution_key = await self._create_execution_lock(
            job_id, scheduled_for
        )
        if not acquired:
            # Another worker already executed this fire time. Release the row-level
            # lock that claim_due_jobs placed on the row so the job is not stuck
            # in 'running' until stale-lock recovery fires (30 min later).
            # We also advance next_run_at so the same execution_key is never hit
            # again, breaking the otherwise-infinite claim → duplicate → recover loop.
            try:
                next_run_at = self._compute_next_run_at(
                    job_row['cron_expr'], job_row['timezone']
                )
            except Exception:
                next_run_at = datetime.now(timezone.utc) + timedelta(minutes=10)
            await self._unlock_job(
                job_id=job_id,
                status='active',
                retry_count=int(job_row['retry_count']),
                last_error=None,
                next_run_at=next_run_at,
            )
            return

        job_exc: Exception | None = None
        try:
            if job_row['job_type'] != 'email_dynamic_query':
                raise ValueError(f"Unsupported job_type: {job_row['job_type']}")
            await self._execute_email_dynamic_query_job(
                job_row['payload'], job_row['timezone']
            )
        except Exception as exc:
            job_exc = exc
            logger.error(f'Failed scheduled job {job_id}: {exc}')
        finally:
            # Guaranteed unlock — always runs even if the DB call above throws.
            retry_count = int(job_row['retry_count'])
            if job_exc is None:
                final_status = 'active'
                final_retry_count = 0
                final_error = None
            else:
                retry_count += 1
                final_retry_count = retry_count
                final_status = (
                    'active' if retry_count <= int(job_row['max_retries']) else 'failed'
                )
                final_error = str(job_exc)

            # Compute next_run_at safely; fall back to a 10-minute delay if cron is broken.
            try:
                next_run_at = self._compute_next_run_at(
                    job_row['cron_expr'], job_row['timezone']
                )
            except Exception as cron_exc:
                logger.error(
                    f'Could not compute next_run_at for job {job_id}: {cron_exc}'
                )
                next_run_at = datetime.now(timezone.utc) + timedelta(minutes=10)

            await self._unlock_job(
                job_id=job_id,
                status=final_status,
                retry_count=final_retry_count,
                last_error=final_error,
                next_run_at=next_run_at,
            )
            execution_status = 'success' if job_exc is None else 'failed'
            await self._complete_execution(
                execution_key, status=execution_status, error=final_error
            )

    async def process_due_jobs(self, batch_size: int = 10):
        due_jobs = await self.claim_due_jobs(batch_size=batch_size)
        for job_row in due_jobs:
            await self._run_job(job_row)

    def process_due_jobs_sync(self, batch_size: int = 10):
        import asyncio

        asyncio.run(self.process_due_jobs(batch_size=batch_size))
