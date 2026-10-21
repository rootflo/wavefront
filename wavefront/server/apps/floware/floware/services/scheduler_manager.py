import os
from typing import Callable

from apscheduler.events import EVENT_JOB_ERROR
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from common_module.log.logger import logger


class SchedulerManager:
    def __init__(self):
        self.scheduler: BackgroundScheduler | None = None

    def _on_scheduler_error(self, event):
        logger.error(f'Scheduler job failed: {event}')

    def _build_scheduler(self) -> BackgroundScheduler:
        # MemoryJobStore avoids pickling the job callable.  Redis persistence
        # is not needed here because:
        #   1. The polling loop is re-registered on every startup (server.py).
        #   2. Distributed deduplication is handled by FOR UPDATE SKIP LOCKED
        #      in claim_due_jobs — not by APScheduler's job store.
        executors = {'default': ThreadPoolExecutor(max(1, (os.cpu_count() or 2) - 1))}
        built = BackgroundScheduler(
            jobstores={'default': MemoryJobStore()},
            executors=executors,
            job_defaults={'coalesce': False, 'max_instances': 3},
            timezone='Asia/Kolkata',
        )
        built.add_listener(self._on_scheduler_error, EVENT_JOB_ERROR)
        return built

    def start(self):
        if self.scheduler is None:
            self.scheduler = self._build_scheduler()
        if not self.scheduler.running:
            self.scheduler.start()

    def register_due_jobs_poller(self, callback: Callable):
        if self.scheduler is None:
            raise RuntimeError('Scheduler must be started before registering jobs')
        self.scheduler.add_job(
            callback,
            trigger=CronTrigger(minute='*/10'),
            id='scheduled-job-poller',
            replace_existing=True,
        )

    def register_stale_lock_recovery(self, callback: Callable):
        """Runs every 15 minutes to reset jobs stuck in 'running' by crashed workers."""
        if self.scheduler is None:
            raise RuntimeError('Scheduler must be started before registering jobs')
        self.scheduler.add_job(
            callback,
            trigger=CronTrigger(minute='*/15'),
            id='stale-lock-recovery',
            replace_existing=True,
        )

    def shutdown(self):
        if self.scheduler and self.scheduler.running:
            # wait=True ensures in-flight jobs finish before shutdown,
            # avoiding jobs left permanently locked in 'running'.
            self.scheduler.shutdown(wait=True)
