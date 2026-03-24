import os
from typing import Callable

from apscheduler.events import EVENT_JOB_ERROR
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from common_module.log.logger import logger


class SchedulerManager:
    def __init__(self, config):
        self.config = config
        self.scheduler: BackgroundScheduler | None = None

    def _on_scheduler_error(self, event):
        logger.error(f'Scheduler job failed: {event}')

    def _build_scheduler(self) -> BackgroundScheduler:
        redis_store = RedisJobStore(
            jobs_key='apscheduler.jobs',
            run_times_key='apscheduler.run_times',
            host=self.config['redis']['host'],
            port=int(self.config['redis']['port']),
        )
        executors = {'default': ThreadPoolExecutor(max(1, (os.cpu_count() or 2) - 1))}
        built = BackgroundScheduler(
            jobstores={'default': redis_store},
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
